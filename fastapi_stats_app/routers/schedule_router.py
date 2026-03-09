from fastapi import APIRouter, Depends, HTTPException, Query
from shared_lib.services.university_api import create_ruz_api_client, RuzAPIError
from shared_lib.services.schedule_service import get_unique_modules_hybrid, get_module_name, get_schedule_with_cache_fallback
from shared_lib.database import get_all_short_names, search_cached_entities, get_db_session_dependency, get_discipline_modules_map
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import aiohttp
from datetime import date, timedelta, datetime
import logging

router = APIRouter(prefix="/schedule", tags=["schedule"])
logger = logging.getLogger(__name__)

@router.get("/search")
async def search_entity(term: str, type: str = "group", db: AsyncSession = Depends(get_db_session_dependency)):
    async with aiohttp.ClientSession() as session:
        client = create_ruz_api_client(session)
        try:
            return await client.search(term, type)
        except RuzAPIError as e:
            logger.warning(f"RUZ API Search failed for '{term}'. Falling back to local cache.")
            cached_results = await search_cached_entities(db, term, type)
            if cached_results:
                return cached_results
            raise HTTPException(status_code=503, detail="API ВУЗа недоступно, а в кэше совпадений не найдено")
        except Exception as e:
            logger.error(f"Unexpected error during search: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

@router.get("/cached_list")
async def get_cached_list(db: AsyncSession = Depends(get_db_session_dependency)):
    """Возвращает список недавно закэшированных групп для правой панели."""
    stmt = text("""
        SELECT entity_type, entity_id, 
               MAX(elem->>'group') as group_name
        FROM cached_schedules, jsonb_array_elements(schedule_data) as elem
        WHERE entity_type = 'group' AND elem->>'group' IS NOT NULL
        GROUP BY entity_type, entity_id, updated_at
        ORDER BY updated_at DESC
    """)
    result = await db.execute(stmt)
    return[{"id": r.entity_id, "type": r.entity_type, "label": r.group_name} for r in result if r.group_name]

@router.get("/data/{type}/{id}")
async def get_schedule_data(
    type: str, 
    id: str, 
    base_date: str = Query(None), # Ожидаем YYYY-MM-DD
    db: AsyncSession = Depends(get_db_session_dependency)
):
    if base_date:
        center_date = datetime.strptime(base_date, "%Y-%m-%d").date()
    else:
        center_date = date.today()
        
    # Парсим ±14 дней от запрошенной даты (4 недели)
    start_date = center_date - timedelta(days=14)
    finish_date = center_date + timedelta(days=14) 
    
    start = start_date.strftime("%Y-%m-%d")
    finish = finish_date.strftime("%Y-%m-%d")
    
    async with aiohttp.ClientSession() as session:
        client = create_ruz_api_client(session)
        try:
            schedule, is_offline = await get_schedule_with_cache_fallback(
                client, type, id, start, finish, max_cache_age_hours=6
            )
            
            short_names = await get_all_short_names()
            discipline_to_module = await get_discipline_modules_map() 
            
            for lesson in schedule:
                full_name = lesson.get('discipline', '')
                lesson['discipline_short'] = short_names.get(full_name, full_name)
                # Оставляем оригинальное имя тоже, чтобы фронт мог переключать!
                lesson['discipline_full'] = full_name 
                
                group_val = lesson.get('group')
                explicit_mod = get_module_name(group_val) if isinstance(group_val, str) else None
                mapped_mod = discipline_to_module.get(full_name)
                lesson['module'] = mapped_mod if mapped_mod else explicit_mod

            modules = await get_unique_modules_hybrid(schedule)
            
            return {
                "schedule": schedule,
                "available_modules": modules,
                "is_offline": is_offline,
                "loaded_bounds": {"start": start, "end": finish} # Отдаем фронту границы загруженного
            }
        except ConnectionError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            logger.error(f"Failed to fetch schedule for website: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")
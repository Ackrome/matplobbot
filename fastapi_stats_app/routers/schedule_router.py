from fastapi import APIRouter, Depends, HTTPException
from shared_lib.services.university_api import create_ruz_api_client, RuzAPIError
from shared_lib.services.schedule_service import get_unique_modules_hybrid, get_module_name, get_schedule_with_cache_fallback
from shared_lib.database import get_all_short_names, search_cached_entities, get_db_session_dependency # Добавлен импорт
from sqlalchemy.ext.asyncio import AsyncSession
import aiohttp
from datetime import date, timedelta
import logging

router = APIRouter(prefix="/schedule", tags=["schedule"])
logger = logging.getLogger(__name__)

@router.get("/search")
async def search_entity(term: str, type: str = "group", db: AsyncSession = Depends(get_db_session_dependency)):
    async with aiohttp.ClientSession() as session:
        client = create_ruz_api_client(session)
        try:
            # 1. Сначала честно пытаемся найти через API ВУЗа
            return await client.search(term, type)
        except RuzAPIError as e:
            logger.warning(f"RUZ API Search failed for '{term}'. Falling back to local cache. Reason: {e}")
            
            # 2. Если упало, ищем в нашей базе!
            cached_results = await search_cached_entities(db, term, type)
            if cached_results:
                return cached_results
                
            # Если и в кэше ничего нет, отдаем ошибку
            raise HTTPException(status_code=503, detail="API ВУЗа недоступно, а в кэше совпадений не найдено")
        except Exception as e:
            logger.error(f"Unexpected error during search: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

@router.get("/data/{type}/{id}")
async def get_schedule_data(type: str, id: str):
    start = date.today().strftime("%Y-%m-%d")
    finish = (date.today() + timedelta(days=14)).strftime("%Y-%m-%d") # Грузим на 2 недели вперед
    
    async with aiohttp.ClientSession() as session:
        client = create_ruz_api_client(session)
        try:
            schedule, is_offline = await get_schedule_with_cache_fallback(
                client, type, id, start, finish, max_cache_age_hours=6
            )
            
            short_names = await get_all_short_names()
            
            for lesson in schedule:
                full_name = lesson.get('discipline', '')
                lesson['discipline_display'] = short_names.get(full_name, full_name)
                lesson['module'] = get_module_name(lesson.get('group')) 

            modules = await get_unique_modules_hybrid(schedule)
            
            return {
                "schedule": schedule,
                "available_modules": modules,
                "is_offline": is_offline
            }
        except ConnectionError as e:
            # Кэша нет и API лежит
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            logger.error(f"Failed to fetch schedule for website: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")
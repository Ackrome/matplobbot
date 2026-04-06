import logging
from datetime import date, datetime, timedelta

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared_lib.database import (
    get_all_short_names,
    get_db_session_dependency,
    get_discipline_modules_map,
    search_cached_entities,
)
from shared_lib.services.schedule_service import (
    get_module_name,
    get_schedule_with_cache_fallback,
    get_unique_modules_hybrid,
)
from shared_lib.services.university_api import RuzAPIError, create_ruz_api_client

router = APIRouter(prefix="/schedule", tags=["schedule"])
logger = logging.getLogger(__name__)
SEARCH_ENTITY_TYPES = ("group", "person", "auditorium")
SEARCH_TYPE_ALIASES = {
    "all": "all",
    "group": "group",
    "person": "person",
    "lecturer": "person",
    "teacher": "person",
    "auditorium": "auditorium",
    "room": "auditorium",
}
SEARCH_TYPE_DESCRIPTIONS = {
    "group": "Group",
    "person": "Lecturer",
    "auditorium": "Auditorium",
}


def get_shared_http_session(request: Request) -> aiohttp.ClientSession:
    http_session = getattr(request.app.state, "shared_http_session", None)
    if not http_session or http_session.closed:
        raise HTTPException(status_code=503, detail="Shared HTTP client session is unavailable")
    return http_session


def _normalize_search_type(search_type: str | None) -> str:
    normalized = SEARCH_TYPE_ALIASES.get((search_type or "all").strip().lower())
    if not normalized:
        raise HTTPException(
            status_code=400,
            detail="Unsupported schedule search type. Use all, group, person, or auditorium.",
        )
    return normalized


def _normalize_search_results(
    raw_results: list[dict] | None, entity_type: str, *, is_offline: bool = False
) -> list[dict]:
    normalized_results = []
    default_description = SEARCH_TYPE_DESCRIPTIONS[entity_type]

    for item in raw_results or []:
        item_id = str(item.get("id") or "").strip()
        label = str(item.get("label") or item.get("name") or "").strip()
        if not item_id or not label:
            continue

        normalized_results.append(
            {
                "id": item_id,
                "label": label,
                "description": str(item.get("description") or default_description),
                "type": entity_type,
                "is_offline": bool(item.get("is_offline", is_offline)),
            }
        )

    return normalized_results


async def _search_single_entity_type(
    term: str,
    entity_type: str,
    db: AsyncSession,
    client,
    *,
    strict_unavailable: bool,
) -> tuple[list[dict], bool]:
    try:
        api_results = await client.search(term, entity_type)
        return _normalize_search_results(api_results, entity_type), False
    except RuzAPIError:
        logger.warning(
            "RUZ API search failed for '%s' (%s). Falling back to local cache.",
            term,
            entity_type,
        )
        cached_results = await search_cached_entities(db, term, entity_type)
        normalized_cached = _normalize_search_results(cached_results, entity_type, is_offline=True)
        if normalized_cached:
            return normalized_cached, False
        if strict_unavailable:
            raise HTTPException(
                status_code=503,
                detail="University search is unavailable and no cached matches were found.",
            )
        return [], True
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Unexpected error during schedule search for '%s' (%s): %s",
            term,
            entity_type,
            e,
            exc_info=True,
        )
        if strict_unavailable:
            raise HTTPException(status_code=500, detail="Internal server error")
        return [], True


def _merge_search_results(results_by_type: dict[str, list[dict]]) -> list[dict]:
    merged_results = []
    seen_ids: set[tuple[str, str]] = set()

    for entity_type in SEARCH_ENTITY_TYPES:
        for item in results_by_type.get(entity_type, []):
            identity = (item["type"], item["id"])
            if identity in seen_ids:
                continue
            seen_ids.add(identity)
            merged_results.append(item)

    return merged_results[:30]


@router.get("/search")
async def search_entity(
    term: str,
    type: str = "all",
    db: AsyncSession = Depends(get_db_session_dependency),
    http_session: aiohttp.ClientSession = Depends(get_shared_http_session),
):
    search_type = _normalize_search_type(type)
    client = create_ruz_api_client(http_session)

    if search_type != "all":
        results, _ = await _search_single_entity_type(
            term,
            search_type,
            db,
            client,
            strict_unavailable=True,
        )
        return results

    results_by_type: dict[str, list[dict]] = {}
    unavailable_types = 0

    for entity_type in SEARCH_ENTITY_TYPES:
        results, is_unavailable = await _search_single_entity_type(
            term,
            entity_type,
            db,
            client,
            strict_unavailable=False,
        )
        results_by_type[entity_type] = results
        if is_unavailable:
            unavailable_types += 1

    merged_results = _merge_search_results(results_by_type)
    if merged_results:
        return merged_results

    if unavailable_types == len(SEARCH_ENTITY_TYPES):
        raise HTTPException(
            status_code=503,
            detail="University search is unavailable and no cached matches were found.",
        )

    return []

    client = create_ruz_api_client(http_session)
    try:
        return await client.search(term, type)
    except RuzAPIError:
        logger.warning(f"RUZ API Search failed for '{term}'. Falling back to local cache.")
        cached_results = await search_cached_entities(db, term, type)
        if cached_results:
            return cached_results
        raise HTTPException(
            status_code=503,
            detail="API ВУЗа недоступно, а в кэше совпадений не найдено",
        )
    except Exception as e:
        logger.error(f"Unexpected error during search: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/cached_list")
async def get_cached_list(db: AsyncSession = Depends(get_db_session_dependency)):
    """Возвращает список недавно закэшированных групп для правой панели."""
    stmt = text(
        """
        SELECT entity_type, entity_id,
               MAX(elem->>'group') as group_name
        FROM cached_schedules, jsonb_array_elements(schedule_data) as elem
        WHERE entity_type = 'group' AND elem->>'group' IS NOT NULL
        GROUP BY entity_type, entity_id, updated_at
        ORDER BY updated_at DESC
    """
    )
    result = await db.execute(stmt)
    return [
        {"id": r.entity_id, "type": r.entity_type, "label": r.group_name}
        for r in result
        if r.group_name
    ]


@router.get("/data/{type}/{id}")
async def get_schedule_data(
    type: str,
    id: str,
    base_date: str = Query(None),  # Ожидаем YYYY-MM-DD
    db: AsyncSession = Depends(get_db_session_dependency),
    http_session: aiohttp.ClientSession = Depends(get_shared_http_session),
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

    client = create_ruz_api_client(http_session)
    try:
        schedule, is_offline = await get_schedule_with_cache_fallback(
            client, type, id, start, finish, max_cache_age_hours=6
        )

        short_names = await get_all_short_names()
        discipline_to_module = await get_discipline_modules_map()

        for lesson in schedule:
            full_name = lesson.get("discipline", "")
            lesson["discipline_short"] = short_names.get(full_name, full_name)
            # Оставляем оригинальное имя тоже, чтобы фронт мог переключать.
            lesson["discipline_full"] = full_name

            group_val = lesson.get("group")
            explicit_mod = get_module_name(group_val) if isinstance(group_val, str) else None
            mapped_mod = discipline_to_module.get(full_name)
            lesson["module"] = mapped_mod if mapped_mod else explicit_mod

        modules = await get_unique_modules_hybrid(schedule)

        return {
            "schedule": schedule,
            "available_modules": modules,
            "is_offline": is_offline,
            "loaded_bounds": {
                "start": start,
                "end": finish,
            },  # Отдаем фронту границы загруженного
        }
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to fetch schedule for website: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

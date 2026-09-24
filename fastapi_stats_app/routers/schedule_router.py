import asyncio
import logging
from datetime import date, timedelta

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared_lib.database import (
    get_all_short_names,
    get_cached_schedule_updated_at,
    get_db_session_dependency,
    get_discipline_modules_map,
    search_cached_entities,
    upsert_cached_schedule,
)
from shared_lib.schemas import (
    CachedScheduleEntitySchema,
    ScheduleCacheBulkRefreshResponse,
    ScheduleDataResponse,
    ScheduleFallbackCountersResponse,
    ScheduleSearchResultSchema,
    ScheduleSemesterRefreshResponse,
)
from shared_lib.services.schedule_freshness import (
    ScheduleUnavailableError,
    get_schedule_with_freshness,
)
from shared_lib.services.schedule_service import (
    get_module_name,
    get_schedule_fallback_counters,
    get_semester_bounds,
    get_unique_modules_hybrid,
    refresh_cached_schedule_entity_ids_and_semester_cache,
)
from shared_lib.services.university_api import RuzAPIError, create_ruz_api_client

from ..auth import require_admin
from ..config import (
    RATE_LIMIT_SCHEDULE_DATA,
    RATE_LIMIT_SCHEDULE_SEARCH,
    SCHEDULE_INITIAL_LIVE_WAIT_SECONDS,
    SCHEDULE_INTERACTIVE_FRESHNESS_SECONDS,
    SCHEDULE_INTERACTIVE_LIVE_WAIT_SECONDS,
    SCHEDULE_INTERACTIVE_UPSTREAM_TIMEOUT_SECONDS,
    SCHEDULE_LEGACY_FRESHNESS_SECONDS,
    SCHEDULE_ON_OPEN_REFRESH_ENABLED,
    SCHEDULE_REFRESH_FAILURE_COOLDOWN_SECONDS,
    SCHEDULE_REFRESH_LOCK_TTL_SECONDS,
)
from ..rate_limit import enforce_rate_limit

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
SEARCH_TYPE_ORDER = {entity_type: index for index, entity_type in enumerate(SEARCH_ENTITY_TYPES)}
SEARCH_TYPE_QUERY_DESCRIPTION = (
    "Search scope for schedule entities. "
    "Allowed values: all, group, person, auditorium. "
    "Aliases: lecturer -> person, teacher -> person, room -> auditorium."
)
SEARCH_TYPE_QUERY_EXAMPLES = ["all", "group", "person", "auditorium", "lecturer", "teacher", "room"]
SEARCH_TERM_MIN_LENGTH = 2


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


def _normalize_search_term(term: str) -> str:
    normalized = term.strip()
    if len(normalized) < SEARCH_TERM_MIN_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Schedule search term must contain at least {SEARCH_TERM_MIN_LENGTH} characters.",
        )
    return normalized


def _normalize_schedule_entity_type(entity_type: str) -> str:
    normalized = str(entity_type or "").strip().lower()
    if normalized not in SEARCH_ENTITY_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported schedule entity type. Use group, person, or auditorium.",
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


async def _resolve_schedule_entity_id(client, entity_type: str, entity_id: str) -> str:
    normalized_id = str(entity_id or "").strip()
    if entity_type not in SEARCH_ENTITY_TYPES or not normalized_id or normalized_id.isdigit():
        return normalized_id

    search = getattr(client, "search", None)
    if not callable(search):
        return normalized_id

    try:
        results = await search(normalized_id, entity_type)
    except Exception:
        logger.warning(
            "RUZ lookup failed while resolving schedule entity id '%s' (%s).",
            normalized_id,
            entity_type,
            exc_info=True,
        )
        return normalized_id

    normalized_lookup = normalized_id.casefold()
    exact_match = next(
        (
            item
            for item in results or []
            if any(
                str(value or "").strip().casefold() == normalized_lookup
                for value in (item.get("label"), item.get("name"), item.get("id"))
            )
        ),
        None,
    )
    match = exact_match or (results[0] if results else None)
    resolved_id = str(match.get("id") or "").strip() if match else ""
    if resolved_id:
        logger.info(
            "Resolved schedule %s identifier '%s' to RUZ id '%s'.",
            entity_type,
            normalized_id,
            resolved_id,
        )
        return resolved_id
    return normalized_id


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
    except RuzAPIError as exc:
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
            ) from exc
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
            raise HTTPException(status_code=500, detail="Internal server error") from e
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

    # Keep ordering deterministic for frontend rendering when relevance ties happen
    # across mixed entity types: fixed type priority, then label/id lexical tie-break.
    merged_results.sort(
        key=lambda item: (
            SEARCH_TYPE_ORDER.get(item["type"], len(SEARCH_ENTITY_TYPES)),
            str(item.get("label", "")).casefold(),
            str(item.get("id", "")).casefold(),
        )
    )
    return merged_results[:30]


@router.get(
    "/search",
    response_model=list[ScheduleSearchResultSchema],
    summary="Search schedule entities",
    description=(
        "Searches groups, lecturers, and auditoriums. Results can mix live university data "
        "with local cache fallback items when the upstream API is degraded."
    ),
)
async def search_entity(
    request: Request,
    term: str = Query(
        ...,
        min_length=SEARCH_TERM_MIN_LENGTH,
        description=(
            "Search term used against schedule entities. "
            f"Must contain at least {SEARCH_TERM_MIN_LENGTH} non-whitespace characters."
        ),
    ),
    type: str = Query(
        "all",
        description=SEARCH_TYPE_QUERY_DESCRIPTION,
        examples=SEARCH_TYPE_QUERY_EXAMPLES,
    ),
    db: AsyncSession = Depends(get_db_session_dependency),
    http_session: aiohttp.ClientSession = Depends(get_shared_http_session),
):
    await enforce_rate_limit(
        request,
        scope="schedule_search",
        settings=RATE_LIMIT_SCHEDULE_SEARCH,
    )
    term = _normalize_search_term(term)
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
    search_results = await asyncio.gather(
        *[
            _search_single_entity_type(
                term,
                entity_type,
                db,
                client,
                strict_unavailable=False,
            )
            for entity_type in SEARCH_ENTITY_TYPES
        ]
    )
    unavailable_types = 0
    for entity_type, (results, is_unavailable) in zip(
        SEARCH_ENTITY_TYPES, search_results, strict=False
    ):
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


@router.get(
    "/cached_list",
    response_model=list[CachedScheduleEntitySchema],
    summary="List recently cached schedule entities",
)
async def get_cached_list(db: AsyncSession = Depends(get_db_session_dependency)):
    """Returns recently cached schedule entities for the offline drawer."""
    stmt = text(
        """
        SELECT cs.entity_type,
               cs.entity_id,
               cs.updated_at,
               COALESCE(NULLIF(cs.entity_name, ''), cs.entity_id) AS label
        FROM cached_schedules cs
        ORDER BY updated_at DESC
        LIMIT 60
    """
    )
    result = await db.execute(stmt)
    return [
        {
            "id": r.entity_id,
            "type": r.entity_type,
            "label": r.label,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in result
        if r.label
    ]


@router.get(
    "/fallback_counters",
    response_model=ScheduleFallbackCountersResponse,
    dependencies=[Depends(require_admin)],
    summary="Get schedule source fallback counters",
)
async def get_fallback_counters():
    """Returns counters for schedule source outcomes: API success, cache fallback, and no cache."""
    return await get_schedule_fallback_counters()


@router.post(
    "/cache/refresh_all_semester",
    response_model=ScheduleCacheBulkRefreshResponse,
    dependencies=[Depends(require_admin)],
    summary="Refresh all semester schedule caches",
    description=(
        "Admin-only endpoint that searches every cached/subscribed schedule entity by "
        "name, remaps stale RUZ ids, updates subscription/calendar references, and "
        "refreshes the current semester cache."
    ),
)
async def refresh_all_schedule_cache_semester(
    http_session: aiohttp.ClientSession = Depends(get_shared_http_session),
):
    client = create_ruz_api_client(http_session)
    try:
        return await refresh_cached_schedule_entity_ids_and_semester_cache(client)
    except Exception as e:
        logger.error("Failed to refresh all schedule caches: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/cache/{type}/{id}/refresh_semester",
    response_model=ScheduleSemesterRefreshResponse,
    dependencies=[Depends(require_admin)],
    summary="Force refresh full-semester schedule cache",
    description=(
        "Admin-only endpoint that fetches the current semester directly from RUZ and "
        "overwrites the local cache for the requested schedule entity. Non-numeric "
        "group, lecturer, and auditorium identifiers are resolved through RUZ search."
    ),
)
async def refresh_schedule_semester_cache(
    type: str,
    id: str,
    http_session: aiohttp.ClientSession = Depends(get_shared_http_session),
):
    entity_type = _normalize_schedule_entity_type(type)
    requested_id = str(id or "").strip()
    if not requested_id:
        raise HTTPException(status_code=422, detail="Schedule entity id is required.")

    start, finish = get_semester_bounds()
    client = create_ruz_api_client(http_session)
    try:
        resolved_id = await _resolve_schedule_entity_id(client, entity_type, requested_id)
        schedule = await client.get_schedule(entity_type, resolved_id, start=start, finish=finish)
        await upsert_cached_schedule(entity_type, resolved_id, schedule)
        source_updated_at = await get_cached_schedule_updated_at(entity_type, resolved_id)

        return {
            "entity_type": entity_type,
            "entity_id": resolved_id,
            "requested_id": requested_id,
            "lesson_count": len(schedule),
            "semester_bounds": {
                "start": start,
                "end": finish,
            },
            "updated_at": source_updated_at.isoformat() if source_updated_at else None,
        }
    except HTTPException:
        raise
    except RuzAPIError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        logger.error("Failed to force-refresh semester schedule cache: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/data/{type}/{id}",
    response_model=ScheduleDataResponse,
    summary="Load a schedule window for a specific entity",
    description=(
        "Returns a centered 29-day schedule window, module metadata, offline-mode signal, "
        "and the loaded date bounds used by the frontend."
    ),
)
async def get_schedule_data(
    request: Request,
    type: str,
    id: str,
    base_date: date | None = Query(
        None,
        description="Optional center date in YYYY-MM-DD. Invalid format returns 422.",
    ),
    refresh: bool = Query(
        False,
        description="Force a live refresh attempt even when a fresh local cache exists.",
    ),
    db: AsyncSession = Depends(get_db_session_dependency),
    http_session: aiohttp.ClientSession = Depends(get_shared_http_session),
):
    await enforce_rate_limit(
        request,
        scope="schedule_data",
        settings=RATE_LIMIT_SCHEDULE_DATA,
    )
    center_date = base_date or date.today()
    entity_type = _normalize_schedule_entity_type(type)

    # Build a +/- 14 day window from the selected center date.
    start_date = center_date - timedelta(days=14)
    finish_date = center_date + timedelta(days=14)

    start = start_date.strftime("%Y-%m-%d")
    finish = finish_date.strftime("%Y-%m-%d")

    client = create_ruz_api_client(
        http_session,
        max_retries=1,
        request_timeout_seconds=SCHEDULE_INTERACTIVE_UPSTREAM_TIMEOUT_SECONDS,
    )
    try:
        resolved_id = await _resolve_schedule_entity_id(client, entity_type, id)
        freshness_seconds = (
            SCHEDULE_INTERACTIVE_FRESHNESS_SECONDS
            if SCHEDULE_ON_OPEN_REFRESH_ENABLED
            else SCHEDULE_LEGACY_FRESHNESS_SECONDS
        )
        freshness_result = await get_schedule_with_freshness(
            client,
            entity_type,
            resolved_id,
            start,
            finish,
            freshness_seconds=freshness_seconds,
            live_wait_seconds=SCHEDULE_INTERACTIVE_LIVE_WAIT_SECONDS,
            initial_live_wait_seconds=SCHEDULE_INITIAL_LIVE_WAIT_SECONDS,
            lock_ttl_seconds=SCHEDULE_REFRESH_LOCK_TTL_SECONDS,
            failure_cooldown_seconds=SCHEDULE_REFRESH_FAILURE_COOLDOWN_SECONDS,
            force_refresh=refresh,
        )
        schedule = freshness_result.schedule

        short_names = await get_all_short_names()
        discipline_to_module = await get_discipline_modules_map()

        for lesson in schedule:
            full_name = lesson.get("discipline", "")
            lesson["discipline_short"] = short_names.get(full_name, full_name)
            # Keep full discipline name so frontend can toggle between short/full.
            lesson["discipline_full"] = full_name

            group_val = lesson.get("group")
            explicit_mod = get_module_name(group_val) if isinstance(group_val, str) else None
            mapped_mod = discipline_to_module.get(full_name)
            lesson["module"] = mapped_mod if mapped_mod else explicit_mod

        modules = await get_unique_modules_hybrid(schedule)
        source_checked_at = freshness_result.source_checked_at
        source_checked_at_value = source_checked_at.isoformat() if source_checked_at else None

        return {
            "schedule": schedule,
            "available_modules": modules,
            "is_offline": freshness_result.is_offline,
            "source_updated_at": source_checked_at_value,
            "source_checked_at": source_checked_at_value,
            "freshness": freshness_result.freshness,
            "refresh_in_progress": freshness_result.refresh_in_progress,
            "cache_age_seconds": freshness_result.cache_age_seconds,
            "content_changed": freshness_result.content_changed,
            "loaded_bounds": {
                "start": start,
                "end": finish,
            },  # Return loaded date bounds for frontend pagination/navigation logic.
        }
    except HTTPException:
        raise
    except ScheduleUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Failed to fetch schedule for website: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e

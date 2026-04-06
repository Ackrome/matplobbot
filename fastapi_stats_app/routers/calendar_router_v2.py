import hashlib
import logging
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from email.utils import format_datetime, parsedate_to_datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from shared_lib.database import (
    get_db_session_dependency,
    get_or_create_calendar_secret,
    get_user_id_by_calendar_secret,
    get_user_subscriptions,
    regenerate_calendar_secret,
)
from shared_lib.models import CachedSchedule, WebAccount
from shared_lib.redis_client import redis_client
from shared_lib.schemas import (
    CalendarSubscriptionProfileCreateRequest,
    CalendarSubscriptionProfileSelectRequest,
    CalendarSubscriptionResponse,
    CalendarSubscriptionToggleRequest,
)
from shared_lib.services.schedule_service import (
    generate_profile_ical_from_aggregated_schedule,
    get_aggregated_schedule,
    get_calendar_aggregated_schedule,
)

from ..auth import get_current_user
from ..config import PUBLIC_API_URL

router = APIRouter()
logger = logging.getLogger(__name__)

CALENDAR_SYNC_KEY = "calendar_sync"
CALENDAR_PROFILE_LIMIT = 6
CALENDAR_WINDOW_PAST_DAYS = 14
CALENDAR_WINDOW_FUTURE_DAYS = 90
CALENDAR_TIMEZONE = "Europe/Moscow"
DEFAULT_PROFILE_ID = "all"
BUILT_IN_PROFILES = (
    {
        "id": "all",
        "name": "All classes",
        "kind": "built_in",
        "lesson_mode": "all",
        "can_delete": False,
        "scope_label": "All active Telegram schedule subscriptions",
    },
    {
        "id": "exams",
        "name": "Exams only",
        "kind": "built_in",
        "lesson_mode": "exams_only",
        "can_delete": False,
        "scope_label": "Exams and pass/fail assessments from all active subscriptions",
    },
)


def _get_calendar_base_url(request: Request) -> str:
    if PUBLIC_API_URL:
        return PUBLIC_API_URL
    return str(request.base_url).rstrip("/")


def _to_webcal_url(http_url: str) -> str:
    if http_url.startswith("https://"):
        return http_url.replace("https://", "webcal://", 1)
    if http_url.startswith("http://"):
        return http_url.replace("http://", "webcal://", 1)
    return http_url


def _mask_secret_url(url: str | None) -> str | None:
    if not url:
        return None

    def _mask(match: re.Match[str]) -> str:
        token = match.group(1)
        if len(token) <= 12:
            return f"/cal/{token[:4]}...{token[-4:]}"
        return f"/cal/{token[:8]}...{token[-6:]}"

    return re.sub(r"/cal/([a-f0-9]{16,64})", _mask, url, count=1)


def _build_calendar_links(request: Request, secret: str, profile_id: str) -> dict[str, str]:
    base_url = _get_calendar_base_url(request)
    if profile_id == DEFAULT_PROFILE_ID:
        http_url = f"{base_url}/api/cal/{secret}.ics"
    else:
        quoted_profile = quote(profile_id, safe="")
        http_url = f"{base_url}/api/cal/{secret}/profiles/{quoted_profile}.ics"

    return {
        "http_url": http_url,
        "webcal_url": _to_webcal_url(http_url),
        "download_url": f"{http_url}?download=1",
        "preview_url": http_url,
        "masked_http_url": _mask_secret_url(http_url) or http_url,
    }


def _default_calendar_sync_state() -> dict:
    return {
        "enabled": True,
        "selected_profile_id": DEFAULT_PROFILE_ID,
        "custom_profiles": [],
        "profile_status": {},
    }


def _normalize_profile_status(raw_status: object) -> dict[str, dict[str, str]]:
    if not isinstance(raw_status, dict):
        return {}

    normalized: dict[str, dict[str, str]] = {}
    for profile_id, value in raw_status.items():
        if not isinstance(value, dict):
            continue
        last_accessed_at = value.get("last_accessed_at")
        if last_accessed_at:
            normalized[str(profile_id)] = {"last_accessed_at": str(last_accessed_at)}
    return normalized


def _normalize_custom_profile(raw_profile: object) -> dict | None:
    if not isinstance(raw_profile, dict):
        return None

    profile_id = str(raw_profile.get("id") or "").strip()
    entity_type = str(raw_profile.get("entity_type") or "").strip()
    entity_id = str(raw_profile.get("entity_id") or "").strip()
    entity_name = str(raw_profile.get("entity_name") or "").strip()
    if not profile_id or not entity_type or not entity_id or not entity_name:
        return None

    lesson_mode = raw_profile.get("lesson_mode")
    if lesson_mode not in {"all", "exams_only"}:
        lesson_mode = "all"

    raw_modules = raw_profile.get("modules") or []
    modules = []
    if isinstance(raw_modules, list):
        modules = sorted({str(module).strip() for module in raw_modules if str(module).strip()})

    name = str(raw_profile.get("name") or entity_name).strip() or entity_name
    return {
        "id": profile_id,
        "name": name,
        "kind": "custom",
        "lesson_mode": lesson_mode,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "entity_name": entity_name,
        "modules": modules,
        "can_delete": True,
    }


def _normalize_calendar_sync_state(preferences: dict | None) -> dict:
    sync_state = _default_calendar_sync_state()
    if not isinstance(preferences, dict):
        return sync_state

    raw_sync = preferences.get(CALENDAR_SYNC_KEY)
    if not isinstance(raw_sync, dict):
        return sync_state

    sync_state["enabled"] = bool(raw_sync.get("enabled", True))
    sync_state["profile_status"] = _normalize_profile_status(raw_sync.get("profile_status"))

    custom_profiles = []
    for raw_profile in raw_sync.get("custom_profiles") or []:
        profile = _normalize_custom_profile(raw_profile)
        if profile:
            custom_profiles.append(profile)
    sync_state["custom_profiles"] = custom_profiles

    valid_ids = {profile["id"] for profile in BUILT_IN_PROFILES} | {
        profile["id"] for profile in custom_profiles
    }
    selected_profile_id = str(raw_sync.get("selected_profile_id") or DEFAULT_PROFILE_ID)
    sync_state["selected_profile_id"] = (
        selected_profile_id if selected_profile_id in valid_ids else DEFAULT_PROFILE_ID
    )
    return sync_state


def _serialize_calendar_sync_state(state: dict) -> dict:
    return {
        "enabled": bool(state.get("enabled", True)),
        "selected_profile_id": str(state.get("selected_profile_id") or DEFAULT_PROFILE_ID),
        "custom_profiles": [
            {
                "id": profile["id"],
                "name": profile["name"],
                "entity_type": profile["entity_type"],
                "entity_id": str(profile["entity_id"]),
                "entity_name": profile["entity_name"],
                "lesson_mode": profile["lesson_mode"],
                "modules": list(profile.get("modules", [])),
            }
            for profile in state.get("custom_profiles", [])
            if profile.get("id")
        ],
        "profile_status": dict(state.get("profile_status", {})),
    }


async def _save_calendar_sync_state(
    account: WebAccount | None, db: AsyncSession, state: dict
) -> None:
    if not account:
        return

    preferences = dict(account.preferences or {})
    preferences[CALENDAR_SYNC_KEY] = _serialize_calendar_sync_state(state)
    account.preferences = preferences
    db.add(account)
    await db.commit()
    await db.refresh(account)


def _build_eligibility(telegram_id: int | None, active_subs: list[dict]) -> dict:
    has_telegram_link = bool(telegram_id)
    has_active_subscriptions = bool(active_subs)
    reasons: list[str] = []

    if not has_telegram_link:
        reasons.append("telegram_link_required")
    if has_telegram_link and not has_active_subscriptions:
        reasons.append("active_schedule_subscription_required")

    if not has_telegram_link:
        detail = "Link this website account to Telegram to unlock private iCal feeds."
    elif not has_active_subscriptions:
        detail = "Create at least one active schedule subscription in the bot to populate the website feed."
    else:
        detail = "Your feed is ready to sync with external calendar apps."

    return {
        "available": has_telegram_link and has_active_subscriptions,
        "has_telegram_link": has_telegram_link,
        "has_active_subscriptions": has_active_subscriptions,
        "reasons": reasons,
        "detail": detail,
    }


def _build_source_summary(all_subs: list[dict], active_subs: list[dict]) -> dict:
    active_entities = {(sub["entity_type"], str(sub["entity_id"])) for sub in active_subs}
    return {
        "total_subscriptions": len(all_subs),
        "active_subscriptions": len(active_subs),
        "active_entities": len(active_entities),
    }


def _build_profile_definitions(sync_state: dict) -> list[dict]:
    return [dict(profile) for profile in BUILT_IN_PROFILES] + [
        dict(profile) for profile in sync_state.get("custom_profiles", [])
    ]


def _find_profile_definition(sync_state: dict, profile_id: str) -> dict | None:
    for profile in _build_profile_definitions(sync_state):
        if profile["id"] == profile_id:
            return profile
    return None


def _profile_scope_label(profile: dict) -> str:
    if profile.get("kind") == "built_in":
        return str(profile.get("scope_label") or "")

    entity_name = profile.get("entity_name") or profile.get("name") or "Current view"
    modules = profile.get("modules") or []
    lesson_mode = profile.get("lesson_mode", "all")
    if modules and lesson_mode == "exams_only":
        return f"{entity_name} with {len(modules)} selected module(s), exams only"
    if modules:
        return f"{entity_name} with {len(modules)} selected module(s)"
    if lesson_mode == "exams_only":
        return f"{entity_name}, exams only"
    return f"{entity_name}, current page scope"


def _count_profile_subscriptions(profile: dict, active_subs: list[dict]) -> int:
    if profile.get("kind") == "built_in":
        return len(active_subs)

    entity_type = profile.get("entity_type")
    entity_id = str(profile.get("entity_id"))
    return sum(
        1
        for sub in active_subs
        if sub["entity_type"] == entity_type and str(sub["entity_id"]) == entity_id
    )


def _filter_schedule_for_profile(schedule: list[dict], profile: dict) -> list[dict]:
    entity_type = profile.get("entity_type")
    entity_id = str(profile.get("entity_id") or "")
    selected_modules = set(profile.get("modules") or [])
    lesson_mode = profile.get("lesson_mode", "all")

    filtered_schedule = []
    for lesson in schedule:
        if entity_type and lesson.get("source_entity_type") != entity_type:
            continue
        if entity_id and str(lesson.get("source_entity_id")) != entity_id:
            continue
        if lesson_mode == "exams_only" and lesson.get("simple_type") != "Exam":
            continue

        module_name = lesson.get("module")
        if selected_modules and module_name and module_name not in selected_modules:
            continue

        filtered_schedule.append(lesson)

    return filtered_schedule


def _lesson_start(lesson: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(f"{lesson['date']}T{lesson['beginLesson']}+03:00")
    except (KeyError, ValueError):
        return None


def _build_next_event(schedule: list[dict]) -> tuple[str | None, str | None]:
    now = datetime.now(UTC)
    future_lessons = []
    for lesson in schedule:
        start_dt = _lesson_start(lesson)
        if start_dt and start_dt.astimezone(UTC) >= now:
            future_lessons.append((start_dt, lesson))

    if not future_lessons:
        return None, None

    next_start, next_lesson = min(future_lessons, key=lambda item: item[0])
    lesson_type = next_lesson.get("simple_type") or next_lesson.get("kindOfWork") or "Class"
    lesson_label = f"{next_lesson.get('discipline', 'Class')} ({lesson_type})"
    return next_start.astimezone(UTC).isoformat(), lesson_label


async def _get_source_update_map(
    db: AsyncSession,
    active_subs: list[dict],
) -> dict[tuple[str, str], datetime]:
    source_keys = {(sub["entity_type"], str(sub["entity_id"])) for sub in active_subs}
    if not source_keys:
        return {}

    stmt = select(
        CachedSchedule.entity_type,
        CachedSchedule.entity_id,
        CachedSchedule.updated_at,
    ).where(tuple_(CachedSchedule.entity_type, CachedSchedule.entity_id).in_(list(source_keys)))
    result = await db.execute(stmt)

    source_update_map: dict[tuple[str, str], datetime] = {}
    for entity_type, entity_id, updated_at in result.all():
        if updated_at is None:
            continue
        source_update_map[(entity_type, str(entity_id))] = updated_at
    return source_update_map


def _build_profile_health(
    profile: dict,
    filtered_schedule: list[dict],
    source_update_map: dict[tuple[str, str], datetime],
    sync_state: dict,
) -> dict:
    included_sources = {
        (lesson.get("source_entity_type"), str(lesson.get("source_entity_id")))
        for lesson in filtered_schedule
        if lesson.get("source_entity_type") and lesson.get("source_entity_id") is not None
    }
    updated_sources = [
        source_update_map[source_key]
        for source_key in included_sources
        if source_key in source_update_map
    ]
    next_event_at, next_event_label = _build_next_event(filtered_schedule)
    last_accessed_at = (
        sync_state.get("profile_status", {}).get(profile["id"], {}).get("last_accessed_at")
    )

    if not included_sources:
        cache_status = "empty"
    elif len(updated_sources) == len(included_sources):
        cache_status = "cached"
    else:
        cache_status = "partial-cache"

    source_updated_at = None
    if updated_sources:
        source_updated_at = max(updated_sources).astimezone(UTC).isoformat()

    return {
        "event_count": len(filtered_schedule),
        "next_event_at": next_event_at,
        "next_event_label": next_event_label,
        "last_generated_at": datetime.now(UTC).isoformat(),
        "source_updated_at": source_updated_at,
        "cache_status": cache_status,
        "used_cached_sources": len(updated_sources),
        "total_sources": len(included_sources),
        "last_accessed_at": last_accessed_at,
    }


def _build_calendar_name(profile: dict) -> str:
    if profile["id"] == "exams":
        return "Matplobbot - Exams Only"
    return f"Matplobbot - {profile['name']}"


def _build_calendar_description(profile: dict) -> str:
    return _profile_scope_label(profile)


def _sanitize_filename(profile: dict) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", str(profile.get("id", "calendar"))).strip("-")
    slug = slug or "calendar"
    return f"matplobbot-{slug}.ics"


def _update_profile_access(sync_state: dict, profile_id: str) -> dict:
    next_state = _normalize_calendar_sync_state(
        {CALENDAR_SYNC_KEY: _serialize_calendar_sync_state(sync_state)}
    )
    next_state.setdefault("profile_status", {})
    next_state["profile_status"][profile_id] = {"last_accessed_at": datetime.now(UTC).isoformat()}
    return next_state


async def _build_calendar_subscription_response(
    request: Request,
    current_user: dict,
    db: AsyncSession,
    secret_override: str | None = None,
) -> CalendarSubscriptionResponse:
    telegram_id = current_user.get("telegram_id")
    sync_state = _normalize_calendar_sync_state(current_user.get("preferences"))

    all_subs: list[dict] = []
    active_subs: list[dict] = []
    if telegram_id:
        all_subs, _ = await get_user_subscriptions(telegram_id, page=0, page_size=100)
        active_subs = [subscription for subscription in all_subs if subscription["is_active"]]

    eligibility = _build_eligibility(telegram_id, active_subs)
    source_summary = _build_source_summary(all_subs, active_subs)

    secret = None
    if telegram_id:
        secret = secret_override or await get_or_create_calendar_secret(telegram_id)

    today = date.today()
    start_date = today - timedelta(days=CALENDAR_WINDOW_PAST_DAYS)
    end_date = today + timedelta(days=CALENDAR_WINDOW_FUTURE_DAYS)

    base_schedule = []
    source_update_map: dict[tuple[str, str], datetime] = {}
    if active_subs:
        base_schedule = await get_calendar_aggregated_schedule(active_subs, start_date, end_date)
        source_update_map = await _get_source_update_map(db, active_subs)

    profiles = []
    selected_profile_id = sync_state.get("selected_profile_id", DEFAULT_PROFILE_ID)
    for profile in _build_profile_definitions(sync_state):
        filtered_schedule = _filter_schedule_for_profile(base_schedule, profile)
        links = _build_calendar_links(request, secret, profile["id"]) if secret else {}
        profiles.append(
            {
                "id": profile["id"],
                "name": profile["name"],
                "kind": profile["kind"],
                "lesson_mode": profile.get("lesson_mode", "all"),
                "selected": profile["id"] == selected_profile_id,
                "can_delete": bool(profile.get("can_delete")),
                "entity_type": profile.get("entity_type"),
                "entity_id": profile.get("entity_id"),
                "entity_name": profile.get("entity_name"),
                "modules": list(profile.get("modules", [])),
                "module_count": len(profile.get("modules", [])),
                "subscription_count": _count_profile_subscriptions(profile, active_subs),
                "scope_label": _profile_scope_label(profile),
                "links": links,
                "health": _build_profile_health(
                    profile, filtered_schedule, source_update_map, sync_state
                ),
            }
        )

    selected_profile = next((profile for profile in profiles if profile["selected"]), None)
    selected_links = selected_profile["links"] if selected_profile else {}

    return CalendarSubscriptionResponse(
        enabled=bool(
            sync_state.get("enabled", True) and eligibility["available"] and selected_profile
        ),
        sync_enabled=bool(sync_state.get("enabled", True)),
        selected_profile_id=selected_profile_id,
        profile_limit=CALENDAR_PROFILE_LIMIT,
        http_url=selected_links.get("http_url"),
        webcal_url=selected_links.get("webcal_url"),
        download_url=selected_links.get("download_url"),
        preview_url=selected_links.get("preview_url"),
        masked_http_url=selected_links.get("masked_http_url"),
        eligibility=eligibility,
        source_summary=source_summary,
        profiles=profiles,
    )


async def _get_account_for_current_user(current_user: dict, db: AsyncSession) -> WebAccount | None:
    db_obj = current_user.get("db_obj")
    if isinstance(db_obj, WebAccount):
        return db_obj

    result = await db.execute(select(WebAccount).where(WebAccount.id == current_user["id"]))
    return result.scalar_one_or_none()


def _validate_calendar_sync_user(current_user: dict) -> int:
    telegram_id = current_user.get("telegram_id")
    if not telegram_id:
        raise HTTPException(
            status_code=400,
            detail="Calendar subscription is unavailable for this account",
        )
    return telegram_id


def _build_custom_profile_name(payload: CalendarSubscriptionProfileCreateRequest) -> str:
    name = payload.entity_name.strip()
    if payload.lesson_mode == "exams_only":
        name = f"{name} - exams"
    if payload.modules:
        name = f"{name} ({len(payload.modules)} modules)"
    return name


@router.get(
    "/cal/subscription",
    response_model=CalendarSubscriptionResponse,
    summary="Get the authorized user's calendar subscription configuration",
)
async def get_calendar_subscription(
    request: Request,
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: dict = Depends(get_current_user),
):
    return await _build_calendar_subscription_response(request, current_user, db)


@router.post(
    "/cal/subscription/reset",
    response_model=CalendarSubscriptionResponse,
    summary="Rotate the authorized user's calendar subscription secret",
)
async def reset_calendar_subscription(
    request: Request,
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: dict = Depends(get_current_user),
):
    telegram_id = _validate_calendar_sync_user(current_user)
    secret = await regenerate_calendar_secret(telegram_id)
    return await _build_calendar_subscription_response(
        request,
        current_user,
        db,
        secret_override=secret,
    )


@router.post(
    "/cal/subscription/toggle",
    response_model=CalendarSubscriptionResponse,
    summary="Enable or disable all website calendar feeds for the current user",
)
async def toggle_calendar_subscription(
    payload: CalendarSubscriptionToggleRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: dict = Depends(get_current_user),
):
    _validate_calendar_sync_user(current_user)
    account = await _get_account_for_current_user(current_user, db)
    sync_state = _normalize_calendar_sync_state(current_user.get("preferences"))
    sync_state["enabled"] = bool(payload.enabled)
    await _save_calendar_sync_state(account, db, sync_state)
    current_user["preferences"] = (
        account.preferences if account else current_user.get("preferences", {})
    )
    current_user["db_obj"] = account
    return await _build_calendar_subscription_response(request, current_user, db)


@router.post(
    "/cal/subscription/select",
    response_model=CalendarSubscriptionResponse,
    summary="Select which calendar profile is active in the website UI",
)
async def select_calendar_subscription_profile(
    payload: CalendarSubscriptionProfileSelectRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: dict = Depends(get_current_user),
):
    _validate_calendar_sync_user(current_user)
    account = await _get_account_for_current_user(current_user, db)
    sync_state = _normalize_calendar_sync_state(current_user.get("preferences"))
    if not _find_profile_definition(sync_state, payload.profile_id):
        raise HTTPException(status_code=404, detail="Calendar profile not found")

    sync_state["selected_profile_id"] = payload.profile_id
    await _save_calendar_sync_state(account, db, sync_state)
    current_user["preferences"] = (
        account.preferences if account else current_user.get("preferences", {})
    )
    current_user["db_obj"] = account
    return await _build_calendar_subscription_response(request, current_user, db)


@router.post(
    "/cal/subscription/profiles",
    response_model=CalendarSubscriptionResponse,
    summary="Create a website-owned calendar profile from the current schedule view",
)
async def create_calendar_subscription_profile(
    payload: CalendarSubscriptionProfileCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: dict = Depends(get_current_user),
):
    telegram_id = _validate_calendar_sync_user(current_user)
    account = await _get_account_for_current_user(current_user, db)
    sync_state = _normalize_calendar_sync_state(current_user.get("preferences"))

    all_subs, _ = await get_user_subscriptions(telegram_id, page=0, page_size=100)
    active_subs = [subscription for subscription in all_subs if subscription["is_active"]]
    has_matching_subscription = any(
        subscription["entity_type"] == payload.entity_type
        and str(subscription["entity_id"]) == str(payload.entity_id)
        for subscription in active_subs
    )
    if not has_matching_subscription:
        raise HTTPException(
            status_code=400,
            detail="The current page is not part of your active Telegram subscriptions",
        )

    normalized_modules = sorted({module.strip() for module in payload.modules if module.strip()})
    existing_profile = next(
        (
            profile
            for profile in sync_state["custom_profiles"]
            if profile["entity_type"] == payload.entity_type
            and str(profile["entity_id"]) == str(payload.entity_id)
            and profile["lesson_mode"] == payload.lesson_mode
            and profile.get("modules", []) == normalized_modules
        ),
        None,
    )
    if existing_profile:
        sync_state["selected_profile_id"] = existing_profile["id"]
    else:
        if len(sync_state["custom_profiles"]) >= CALENDAR_PROFILE_LIMIT:
            raise HTTPException(
                status_code=400,
                detail=f"You can keep up to {CALENDAR_PROFILE_LIMIT} website calendar profiles",
            )

        profile_id = f"custom-{uuid.uuid4().hex[:12]}"
        sync_state["custom_profiles"].append(
            {
                "id": profile_id,
                "name": _build_custom_profile_name(payload),
                "kind": "custom",
                "lesson_mode": payload.lesson_mode,
                "entity_type": payload.entity_type,
                "entity_id": str(payload.entity_id),
                "entity_name": payload.entity_name,
                "modules": normalized_modules,
                "can_delete": True,
            }
        )
        sync_state["selected_profile_id"] = profile_id

    await _save_calendar_sync_state(account, db, sync_state)
    current_user["preferences"] = (
        account.preferences if account else current_user.get("preferences", {})
    )
    current_user["db_obj"] = account
    return await _build_calendar_subscription_response(request, current_user, db)


@router.delete(
    "/cal/subscription/profiles/{profile_id}",
    response_model=CalendarSubscriptionResponse,
    summary="Delete a custom website calendar profile",
)
async def delete_calendar_subscription_profile(
    profile_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: dict = Depends(get_current_user),
):
    _validate_calendar_sync_user(current_user)
    account = await _get_account_for_current_user(current_user, db)
    sync_state = _normalize_calendar_sync_state(current_user.get("preferences"))

    next_profiles = [
        profile for profile in sync_state["custom_profiles"] if profile["id"] != profile_id
    ]
    if len(next_profiles) == len(sync_state["custom_profiles"]):
        raise HTTPException(status_code=404, detail="Calendar profile not found")

    sync_state["custom_profiles"] = next_profiles
    sync_state["profile_status"].pop(profile_id, None)
    if sync_state.get("selected_profile_id") == profile_id:
        sync_state["selected_profile_id"] = DEFAULT_PROFILE_ID

    await _save_calendar_sync_state(account, db, sync_state)
    current_user["preferences"] = (
        account.preferences if account else current_user.get("preferences", {})
    )
    current_user["db_obj"] = account
    return await _build_calendar_subscription_response(request, current_user, db)


async def _resolve_public_calendar_context(
    secret_token: str,
    profile_id: str,
    db: AsyncSession,
) -> tuple[int, WebAccount | None, dict, list[dict], dict]:
    clean_token = secret_token.replace(".ics", "")
    telegram_user_id = await get_user_id_by_calendar_secret(clean_token)
    if not telegram_user_id:
        raise HTTPException(status_code=404, detail="Calendar not found")

    account_result = await db.execute(
        select(WebAccount).where(WebAccount.telegram_id == telegram_user_id)
    )
    account = account_result.scalar_one_or_none()
    sync_state = _normalize_calendar_sync_state(account.preferences if account else {})
    if account and not sync_state.get("enabled", True):
        raise HTTPException(status_code=404, detail="Calendar not found")

    profile = _find_profile_definition(sync_state, profile_id)
    if profile_id == DEFAULT_PROFILE_ID and not profile:
        profile = dict(BUILT_IN_PROFILES[0])
    if not profile:
        raise HTTPException(status_code=404, detail="Calendar profile not found")

    all_subs, _ = await get_user_subscriptions(telegram_user_id, page=0, page_size=100)
    active_subs = [subscription for subscription in all_subs if subscription["is_active"]]
    return telegram_user_id, account, sync_state, active_subs, profile


async def _render_public_calendar_feed(
    request: Request,
    secret_token: str,
    profile_id: str,
    db: AsyncSession,
    download: bool,
) -> Response:
    _, account, sync_state, active_subs, profile = await _resolve_public_calendar_context(
        secret_token,
        profile_id,
        db,
    )

    today = date.today()
    start_date = today - timedelta(days=CALENDAR_WINDOW_PAST_DAYS)
    end_date = today + timedelta(days=CALENDAR_WINDOW_FUTURE_DAYS)
    base_schedule = await get_calendar_aggregated_schedule(active_subs, start_date, end_date)
    source_update_map = await _get_source_update_map(db, active_subs)
    filtered_schedule = _filter_schedule_for_profile(base_schedule, profile)
    health = _build_profile_health(profile, filtered_schedule, source_update_map, sync_state)

    ical_bytes = generate_profile_ical_from_aggregated_schedule(
        filtered_schedule,
        calendar_name=_build_calendar_name(profile),
        calendar_description=_build_calendar_description(profile),
        timezone_name=CALENDAR_TIMEZONE,
    )
    etag = f'"{hashlib.sha256(ical_bytes).hexdigest()}"'

    source_updated_at = health.get("source_updated_at")
    last_modified_dt = (
        datetime.fromisoformat(source_updated_at) if source_updated_at else datetime.now(UTC)
    )
    last_modified_dt = last_modified_dt.astimezone(UTC).replace(microsecond=0)

    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=304,
            headers={
                "ETag": etag,
                "Last-Modified": format_datetime(last_modified_dt, usegmt=True),
                "Cache-Control": "private, max-age=0, must-revalidate",
            },
        )

    if_modified_since = request.headers.get("if-modified-since")
    if if_modified_since:
        try:
            parsed_if_modified_since = parsedate_to_datetime(if_modified_since).astimezone(UTC)
            if parsed_if_modified_since >= last_modified_dt:
                return Response(
                    status_code=304,
                    headers={
                        "ETag": etag,
                        "Last-Modified": format_datetime(last_modified_dt, usegmt=True),
                        "Cache-Control": "private, max-age=0, must-revalidate",
                    },
                )
        except (TypeError, ValueError):
            pass

    if account:
        next_state = _update_profile_access(sync_state, profile["id"])
        await _save_calendar_sync_state(account, db, next_state)

    filename = _sanitize_filename(profile)
    disposition = "attachment" if download else "inline"
    return Response(
        content=b"" if request.method == "HEAD" else ical_bytes,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f"{disposition}; filename={filename}",
            "Cache-Control": "private, max-age=0, must-revalidate",
            "ETag": etag,
            "Last-Modified": format_datetime(last_modified_dt, usegmt=True),
        },
    )


async def _render_telegram_filtered_feed(
    request: Request,
    secret_token: str,
    download: bool,
) -> Response:
    clean_token = secret_token.replace(".ics", "")
    telegram_user_id = await get_user_id_by_calendar_secret(clean_token)
    if not telegram_user_id:
        raise HTTPException(status_code=404, detail="Calendar not found")

    all_subs, _ = await get_user_subscriptions(telegram_user_id, page=0, page_size=100)
    active_subs = [subscription for subscription in all_subs if subscription["is_active"]]
    raw_filters = await redis_client.get_user_cache(telegram_user_id, "mysch_filters")
    filters = raw_filters if isinstance(raw_filters, dict) else {"excluded_subs": [], "excluded_types": []}

    today = date.today()
    start_date = today - timedelta(days=CALENDAR_WINDOW_PAST_DAYS)
    end_date = today + timedelta(days=CALENDAR_WINDOW_FUTURE_DAYS)
    aggregated_schedule = await get_aggregated_schedule(
        telegram_user_id,
        active_subs,
        start_date,
        end_date,
        filters,
    )

    ical_bytes = generate_profile_ical_from_aggregated_schedule(
        aggregated_schedule,
        calendar_name="Matplobbot Telegram filtered schedule",
        calendar_description="Personal schedule feed filtered by Telegram subscription settings.",
        timezone_name=CALENDAR_TIMEZONE,
    )
    disposition = "attachment" if download else "inline"
    return Response(
        content=b"" if request.method == "HEAD" else ical_bytes,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'{disposition}; filename="matplobbot-telegram-filtered.ics"',
            "Cache-Control": "private, max-age=0, must-revalidate",
            "Pragma": "no-cache",
        },
    )


@router.api_route(
    "/cal/{secret_token}/basic.ics",
    methods=["GET", "HEAD"],
    summary="Public personal schedule iCal feed",
)
@router.api_route(
    "/cal/{secret_token}.ics",
    methods=["GET", "HEAD"],
    summary="Public personal schedule iCal feed",
)
async def get_webcal_schedule(
    request: Request,
    secret_token: str,
    download: bool = Query(False),
    db: AsyncSession = Depends(get_db_session_dependency),
):
    try:
        return await _render_public_calendar_feed(
            request,
            secret_token,
            DEFAULT_PROFILE_ID,
            db,
            download,
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.error(
            "Error generating calendar feed for secret %s: %s",
            secret_token,
            error,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal Error")


@router.api_route(
    "/cal/{secret_token}/telegram.ics",
    methods=["GET", "HEAD"],
    summary="Public Telegram-filtered personal schedule iCal feed",
)
@router.api_route(
    "/cal/{secret_token}/telegram/basic.ics",
    methods=["GET", "HEAD"],
    summary="Public Telegram-filtered personal schedule iCal feed",
)
async def get_webcal_schedule_telegram_filtered(
    request: Request,
    secret_token: str,
    download: bool = Query(False),
    db: AsyncSession = Depends(get_db_session_dependency),
):
    try:
        _ = db  # keep DB dependency lifecycle consistent with other public feed handlers
        return await _render_telegram_filtered_feed(request, secret_token, download)
    except HTTPException:
        raise
    except Exception as error:
        logger.error(
            "Error generating Telegram-filtered calendar feed for secret %s: %s",
            secret_token,
            error,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal Error")


@router.api_route(
    "/cal/{secret_token}/profiles/{profile_id}.ics",
    methods=["GET", "HEAD"],
    summary="Public profile-specific schedule iCal feed",
)
@router.api_route(
    "/cal/{secret_token}/profiles/{profile_id}/basic.ics",
    methods=["GET", "HEAD"],
    summary="Public profile-specific schedule iCal feed",
)
async def get_webcal_schedule_profile(
    request: Request,
    secret_token: str,
    profile_id: str,
    download: bool = Query(False),
    db: AsyncSession = Depends(get_db_session_dependency),
):
    try:
        return await _render_public_calendar_feed(
            request,
            secret_token,
            profile_id,
            db,
            download,
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.error(
            "Error generating profile calendar feed for secret %s profile %s: %s",
            secret_token,
            profile_id,
            error,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal Error")

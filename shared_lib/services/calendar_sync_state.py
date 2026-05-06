from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from urllib.parse import quote

CALENDAR_SYNC_KEY = "calendar_sync"
CALENDAR_PROFILE_LIMIT = 6
DEFAULT_PROFILE_ID = "all"

BUILT_IN_PROFILES = (
    {
        "id": "all",
        "name": "All classes",
        "kind": "built_in",
        "lesson_mode": "all",
        "can_delete": False,
        "scope_label": "All Telegram subscriptions and website calendar profiles",
    },
    {
        "id": "exams",
        "name": "Exams only",
        "kind": "built_in",
        "lesson_mode": "exams_only",
        "can_delete": False,
        "scope_label": "Exams, pass/fail assessments, and pre-exam consultations from Telegram and website profiles",
    },
)


@dataclass(frozen=True)
class CalendarProfilePayload:
    entity_type: str
    entity_id: str
    entity_name: str
    lesson_mode: str = "all"
    modules: tuple[str, ...] = ()


def default_calendar_sync_state() -> dict:
    return {
        "enabled": True,
        "selected_profile_id": DEFAULT_PROFILE_ID,
        "custom_profiles": [],
        "profile_status": {},
    }


def normalize_profile_status(raw_status: object) -> dict[str, dict[str, str]]:
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


def normalize_custom_profile(raw_profile: object) -> dict | None:
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


def normalize_calendar_sync_state(preferences: dict | None) -> dict:
    sync_state = default_calendar_sync_state()
    if not isinstance(preferences, dict):
        return sync_state

    raw_sync = preferences.get(CALENDAR_SYNC_KEY)
    if not isinstance(raw_sync, dict):
        return sync_state

    sync_state["enabled"] = bool(raw_sync.get("enabled", True))
    sync_state["profile_status"] = normalize_profile_status(raw_sync.get("profile_status"))

    custom_profiles = []
    for raw_profile in raw_sync.get("custom_profiles") or []:
        profile = normalize_custom_profile(raw_profile)
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


def serialize_calendar_sync_state(state: dict) -> dict:
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


def build_profile_definitions(sync_state: dict) -> list[dict]:
    return [dict(profile) for profile in BUILT_IN_PROFILES] + [
        dict(profile) for profile in sync_state.get("custom_profiles", [])
    ]


def find_profile_definition(sync_state: dict, profile_id: str) -> dict | None:
    return next(
        (
            profile
            for profile in build_profile_definitions(sync_state)
            if profile["id"] == profile_id
        ),
        None,
    )


def build_profile_links(base_url: str, secret: str, profile_id: str) -> dict[str, str]:
    clean_base = base_url.rstrip("/")
    if profile_id == DEFAULT_PROFILE_ID:
        http_url = f"{clean_base}/api/cal/{secret}.ics"
    else:
        http_url = f"{clean_base}/api/cal/{secret}/profiles/{quote(profile_id, safe='')}.ics"

    webcal_url = http_url
    if http_url.startswith("https://"):
        webcal_url = http_url.replace("https://", "webcal://", 1)
    elif http_url.startswith("http://"):
        webcal_url = http_url.replace("http://", "webcal://", 1)

    return {
        "http_url": http_url,
        "webcal_url": webcal_url,
        "download_url": f"{http_url}?download=1",
        "preview_url": http_url,
        "masked_http_url": mask_secret_url(http_url) or http_url,
    }


def mask_secret_url(url: str | None) -> str | None:
    if not url:
        return None

    def _mask(match: re.Match[str]) -> str:
        token = match.group(1)
        if len(token) <= 12:
            return f"/cal/{token[:4]}...{token[-4:]}"
        return f"/cal/{token[:8]}...{token[-6:]}"

    return re.sub(r"/cal/([a-f0-9]{16,64})", _mask, url, count=1)


def build_custom_profile_name(payload: CalendarProfilePayload) -> str:
    suffix = "exams" if payload.lesson_mode == "exams_only" else "all"
    module_count = len(payload.modules)
    if module_count:
        suffix += f", {module_count} modules"
    return f"{payload.entity_name} ({suffix})"


def upsert_custom_profile(
    sync_state: dict, payload: CalendarProfilePayload
) -> tuple[dict, dict, bool]:
    normalized_modules = sorted({module.strip() for module in payload.modules if module.strip()})
    next_state = normalize_calendar_sync_state(
        {CALENDAR_SYNC_KEY: serialize_calendar_sync_state(sync_state)}
    )
    existing_profile = next(
        (
            profile
            for profile in next_state["custom_profiles"]
            if profile["entity_type"] == payload.entity_type
            and str(profile["entity_id"]) == str(payload.entity_id)
            and profile["lesson_mode"] == payload.lesson_mode
            and profile.get("modules", []) == normalized_modules
        ),
        None,
    )
    if existing_profile:
        next_state["selected_profile_id"] = existing_profile["id"]
        return next_state, existing_profile, False

    if len(next_state["custom_profiles"]) >= CALENDAR_PROFILE_LIMIT:
        raise ValueError("calendar_profile_limit")

    profile = {
        "id": f"custom-{uuid.uuid4().hex[:12]}",
        "name": build_custom_profile_name(
            CalendarProfilePayload(
                entity_type=payload.entity_type,
                entity_id=str(payload.entity_id),
                entity_name=payload.entity_name,
                lesson_mode=payload.lesson_mode,
                modules=tuple(normalized_modules),
            )
        ),
        "kind": "custom",
        "lesson_mode": payload.lesson_mode,
        "entity_type": payload.entity_type,
        "entity_id": str(payload.entity_id),
        "entity_name": payload.entity_name,
        "modules": normalized_modules,
        "can_delete": True,
    }
    next_state["custom_profiles"].append(profile)
    next_state["selected_profile_id"] = profile["id"]
    return next_state, profile, True

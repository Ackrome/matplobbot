"""Bounded timetable comparison and common free windows from verified schedules."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from shared_lib.schedule_freshness_config import load_schedule_freshness_settings

MAX_ENTITIES = 6
MAX_DAYS = 14
MAX_CONFLICTS = 200
SOURCE_TIMEZONE = ZoneInfo("Europe/Moscow")


def validate_window(
    start_date: date, end_date: date, day_start: time, day_end: time, min_free_minutes: int
) -> None:
    if not 0 <= (end_date - start_date).days < MAX_DAYS:
        raise ValueError("Choose between 1 and 14 days")
    if day_start.tzinfo or day_end.tzinfo or day_start >= day_end:
        raise ValueError("Daily bounds must be local times with start before end")
    if not 5 <= min_free_minutes <= 720:
        raise ValueError("Minimum free duration must be 5–720 minutes")


def analyze_schedules(
    sources: list[dict],
    *,
    start_date: date,
    end_date: date,
    timezone: str = "Europe/Moscow",
    day_start: time = time(8),
    day_end: time = time(22),
    min_free_minutes: int = 30,
) -> dict:
    """Compare real intervals, deduplicating a shared lesson across multiple entities.

    RUZ wall times are Moscow times. Date/time bounds and returned intervals use
    the requested display timezone. Unknown or unverified input never yields free slots.
    """
    validate_window(start_date, end_date, day_start, day_end, min_free_minutes)
    zone = ZoneInfo(timezone)
    if not 1 <= len(sources) <= MAX_ENTITIES:
        raise ValueError("Choose 1–6 schedule entities")
    window_start = datetime.combine(start_date, time.min, zone)
    window_end = datetime.combine(end_date + timedelta(days=1), time.min, zone)
    lessons: dict[tuple[str, ...], dict] = {}
    source_metadata = []
    warnings = set()
    incomplete = False
    for source in sources:
        source_key = f"{source['entity_type']}:{source['entity_id']}"
        metadata = {key: value for key, value in source.items() if key != "schedule"}
        source_metadata.append(metadata)
        if source.get("freshness") not in {"live", "fresh_cache"}:
            incomplete = True
            warnings.add(
                "source_unavailable" if source.get("schedule") is None else "source_unverified"
            )
        schedule = source.get("schedule") or []
        if len(schedule) > 10000:
            incomplete = True
            warnings.add("source_too_large")
            continue
        for lesson in schedule:
            try:
                lesson_date = date.fromisoformat(str(lesson["date"]).replace(".", "-"))
                # Ignore dates well outside the request before parsing their times.
                if (
                    not start_date - timedelta(days=1)
                    <= lesson_date
                    <= end_date + timedelta(days=1)
                ):
                    continue
                begin = time.fromisoformat(str(lesson["beginLesson"]))
                finish = time.fromisoformat(str(lesson["endLesson"]))
                if begin.tzinfo or finish.tzinfo or finish <= begin:
                    raise ValueError("Invalid lesson interval")
                start = datetime.combine(lesson_date, begin, SOURCE_TIMEZONE).astimezone(zone)
                end = datetime.combine(lesson_date, finish, SOURCE_TIMEZONE).astimezone(zone)
            except (KeyError, TypeError, ValueError):
                incomplete = True
                warnings.add("invalid_lesson")
                continue
            if end <= window_start or start >= window_end:
                continue
            identity = (
                start.isoformat(),
                end.isoformat(),
                str(lesson.get("discipline") or ""),
                str(lesson.get("kindOfWork") or ""),
                str(lesson.get("auditorium") or ""),
                str(lesson.get("lecturer_title") or ""),
            )
            if identity in lessons:
                if source_key not in lessons[identity]["sources"]:
                    lessons[identity]["sources"].append(source_key)
                continue
            lessons[identity] = {
                "id": hashlib.sha256("\x1f".join(identity).encode("utf-8")).hexdigest()[:20],
                "start": start.isoformat(),
                "end": end.isoformat(),
                "discipline": identity[2],
                "kind": identity[3],
                "auditorium": identity[4],
                "lecturer": identity[5],
                "sources": [source_key],
            }
    intervals = sorted(lessons.values(), key=lambda item: (item["start"], item["end"], item["id"]))
    conflicts: list[dict] = []
    active: list[dict] = []
    truncated = False
    for lesson in intervals:
        active = [other for other in active if other["end"] > lesson["start"]]
        for other in active:
            if len(conflicts) >= MAX_CONFLICTS:
                truncated = True
                break
            conflicts.append(
                {
                    "start": max(other["start"], lesson["start"]),
                    "end": min(other["end"], lesson["end"]),
                    "lessons": [other, lesson],
                }
            )
        if truncated:
            break
        active.append(lesson)
    free = []
    if not incomplete:
        for offset in range((end_date - start_date).days + 1):
            day = start_date + timedelta(days=offset)
            start = datetime.combine(day, day_start, zone)
            day_finish = datetime.combine(day, day_end, zone)
            busy = []
            for lesson in intervals:
                left = max(start, datetime.fromisoformat(lesson["start"]))
                right = min(day_finish, datetime.fromisoformat(lesson["end"]))
                if left < right:
                    busy.append((left, right))
            cursor = start
            for left, right in sorted(busy) + [(day_finish, day_finish)]:
                minutes = int((left - cursor).total_seconds() // 60)
                if minutes >= min_free_minutes:
                    free.append(
                        {
                            "start": cursor.isoformat(),
                            "end": left.isoformat(),
                            "duration_minutes": minutes,
                        }
                    )
                cursor = max(cursor, right)
    if truncated:
        warnings.add("conflicts_truncated")
    if any(source["entity_type"] == "auditorium" for source in sources):
        warnings.add("room_availability_is_timetable_only")
    return {
        "timezone": timezone,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "conflicts": conflicts,
        "free_windows": free,
        "sources": source_metadata,
        "incomplete": incomplete,
        "warnings": sorted(warnings),
        "lesson_count": len(intervals),
    }


async def load_schedule_plan(
    client,
    entities: list[dict],
    *,
    start_date: date,
    end_date: date,
    timezone: str = "Europe/Moscow",
    day_start: time = time(8),
    day_end: time = time(22),
    min_free_minutes: int = 30,
    excluded_types: set[str] | None = None,
) -> dict:
    """Load each entity once using the shared refresh policy, then compare filtered schedules."""
    from shared_lib.database import get_discipline_modules_map
    from shared_lib.services.schedule_freshness import (
        ScheduleUnavailableError,
        get_schedule_with_freshness,
    )
    from shared_lib.services.schedule_service import (
        _get_simple_lesson_type,
        get_module_name,
        get_semester_bounds,
    )

    validate_window(start_date, end_date, day_start, day_end, min_free_minutes)
    unique_entities = {(entity["entity_type"], str(entity["entity_id"])) for entity in entities}
    if not 1 <= len(unique_entities) <= MAX_ENTITIES:
        raise ValueError("Choose 1–6 schedule entities")
    zone = ZoneInfo(timezone)
    semester_start, semester_end = map(date.fromisoformat, get_semester_bounds())
    source_start = datetime.combine(start_date, day_start, zone).astimezone(SOURCE_TIMEZONE).date()
    source_end = datetime.combine(end_date, day_end, zone).astimezone(SOURCE_TIMEZONE).date()
    if source_start < semester_start or source_end > semester_end:
        raise ValueError("Planning is available inside the currently cached university semester")
    settings = load_schedule_freshness_settings()
    modules = await get_discipline_modules_map()
    grouped: dict[tuple[str, str], list[dict]] = {}
    for entity in entities:
        key = (entity["entity_type"], str(entity["entity_id"]))
        grouped.setdefault(key, []).append(entity)

    async def load(key, profiles):
        entity_type, entity_id = key
        metadata = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "entity_name": profiles[0].get("entity_name") or entity_id,
        }
        try:
            result = await get_schedule_with_freshness(
                client,
                entity_type,
                entity_id,
                (start_date - timedelta(days=1)).isoformat(),
                (end_date + timedelta(days=1)).isoformat(),
                freshness_seconds=settings.effective_freshness_seconds,
                live_wait_seconds=settings.live_wait_seconds,
                initial_live_wait_seconds=settings.initial_live_wait_seconds,
                lock_ttl_seconds=settings.lock_ttl_seconds,
                failure_cooldown_seconds=settings.failure_cooldown_seconds,
            )
        except ScheduleUnavailableError:
            return {
                **metadata,
                "schedule": None,
                "freshness": "unavailable",
                "source_checked_at": None,
            }
        filtered = []
        for lesson in result.schedule:
            if not isinstance(lesson, dict):
                filtered.append({})
                continue
            kind = _get_simple_lesson_type(lesson.get("kindOfWork", ""))
            if kind in (excluded_types or set()):
                continue
            group_name = lesson.get("group")
            module = modules.get(lesson.get("discipline")) or get_module_name(
                group_name if isinstance(group_name, str) else None
            )
            if any(
                (
                    profile.get("lesson_mode", "all") != "exams_only"
                    or kind in {"Exam", "Consultation"}
                )
                and (
                    profile.get("selected_modules") is None
                    or not module
                    or module in profile["selected_modules"]
                )
                for profile in profiles
            ):
                filtered.append(lesson)
        return {
            **metadata,
            "schedule": filtered,
            "freshness": result.freshness,
            "source_checked_at": result.source_checked_at.isoformat()
            if result.source_checked_at
            else None,
        }

    sources = await asyncio.gather(*(load(key, profiles) for key, profiles in grouped.items()))
    return analyze_schedules(
        sources,
        start_date=start_date,
        end_date=end_date,
        timezone=timezone,
        day_start=day_start,
        day_end=day_end,
        min_free_minutes=min_free_minutes,
    )

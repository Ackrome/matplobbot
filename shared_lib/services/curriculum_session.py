"""Serve assessment dates locally and periodically verify approved semesters with RUZ."""

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from shared_lib.database import get_cached_schedule_with_coverage, get_session
from shared_lib.models import CurriculumDocument, CurriculumGroup, CurriculumSessionSnapshot
from shared_lib.services.curriculum_service import match_session_dates, schedule_assessment_kind
from shared_lib.services.university_api import RuzAPIError, create_ruz_api_client

logger = logging.getLogger(__name__)
FRESH_FOR = timedelta(hours=6)
RETRY_AFTER = timedelta(hours=1)
LOOKAHEAD = timedelta(days=45)
MAX_TERM_DAYS = 185
MAX_REQUESTS = 8
_SOURCE_FIELDS = (
    "date",
    "discipline",
    "kindOfWork",
    "beginLesson",
    "auditorium",
    "auditorium_title",
    "deletion_mark",
    "disciplineinplan",
    "disciplineOid",
    "lessonOid",
)


def _utc(stamp):
    if stamp is not None:
        return stamp.astimezone(UTC) if stamp.tzinfo else stamp.replace(tzinfo=UTC)
    return None


def _term_key(group_id, term):
    return (
        group_id,
        term["semester"],
        date.fromisoformat(term["start_date"]),
        date.fromisoformat(term["end_date"]),
    )


def _due(attempted, checked, now):
    return (not checked or now - _utc(checked) >= FRESH_FOR) and (
        not attempted or now - _utc(attempted) >= RETRY_AFTER
    )


def _valid_schedule(lessons, start, end):
    if not isinstance(lessons, list):
        return False
    for row in lessons:
        if not isinstance(row, dict) or any(
            not isinstance(row.get(field), str) for field in ("date", "discipline", "kindOfWork")
        ):
            return False
        try:
            day = date.fromisoformat(row["date"])
        except ValueError:
            return False
        if not (start <= day <= end and day.isoformat() == row["date"]):
            return False
    return True


async def cached_session_dates(group_id: str, term: dict, assessments: list, *, now=None) -> dict:
    """Read a durable term check, using canonical coverage until the first success."""
    now = now or datetime.now(UTC)
    key = _term_key(group_id, term)
    start, end = key[2:]
    async with get_session() as db:
        snapshot = await db.get(CurriculumSessionSnapshot, key)
    checked = _utc(snapshot.checked_at) if snapshot else None
    lower, upper = start, end
    lessons = snapshot.lessons if checked else []
    if not checked:
        payload, stamp, bounds = await get_cached_schedule_with_coverage("group", group_id)
        if bounds and stamp:
            covered_start, covered_end = map(date.fromisoformat, bounds)
            lower = max(start, covered_start)
            upper = min(end, covered_end)
            if lower <= upper and _valid_schedule(payload, covered_start, covered_end):
                checked = _utc(stamp)
                lessons = payload
    status = "unavailable"
    if checked:
        status = "stale" if now - checked >= FRESH_FOR else "checked"
        if (lower, upper) != (start, end):
            status = "partial"
    first, last = lower.isoformat(), upper.isoformat()
    timestamp = checked.isoformat() if checked else None
    return {
        "dates_status": status,
        "dates_coverage": [{"start_date": first, "end_date": last, "checked_at": timestamp}]
        if timestamp
        else [],
        "dates_checked_at": timestamp,
        "events": match_session_dates(assessments, lessons, first, last, group_id=group_id),
    }


async def _due_terms(today, now):
    horizon = today + LOOKAHEAD
    async with get_session() as db:
        groups = (
            await db.execute(
                select(CurriculumGroup.group_id, CurriculumGroup.terms)
                .join(CurriculumDocument, CurriculumDocument.id == CurriculumGroup.document_id)
                .where(
                    CurriculumDocument.published_hash.is_not(None),
                    CurriculumDocument.parent_document_id.is_(None),
                )
            )
        ).all()
        snapshots = (
            await db.execute(
                select(
                    CurriculumSessionSnapshot.group_id,
                    CurriculumSessionSnapshot.semester,
                    CurriculumSessionSnapshot.start_date,
                    CurriculumSessionSnapshot.end_date,
                    CurriculumSessionSnapshot.attempted_at,
                    CurriculumSessionSnapshot.checked_at,
                ).where(
                    CurriculumSessionSnapshot.start_date <= horizon,
                    CurriculumSessionSnapshot.end_date >= today,
                )
            )
        ).all()
        state = {
            (item.group_id, item.semester, item.start_date, item.end_date): (
                item.attempted_at,
                item.checked_at,
            )
            for item in snapshots
        }
    choices = []
    for group_id, terms in groups:
        for term in terms:
            key = _term_key(group_id, term)
            start, end = key[2:]
            if not (start <= horizon and end >= today and 0 <= (end - start).days <= MAX_TERM_DAYS):
                continue
            attempted, checked = state.get(key, (None, None))
            if _due(attempted, checked, now):
                choices.append((_utc(attempted) or datetime.min.replace(tzinfo=UTC), key))
    return [key for _, key in sorted(choices)[:MAX_REQUESTS]]


async def _claim(key, attempted):
    group_id, semester, start, end = key
    async with get_session() as db, db.begin():
        # Serialize competing scheduler workers and recheck the declared term after selection.
        group = await db.get(CurriculumGroup, group_id, with_for_update=True)
        if (
            not group
            or {"semester": semester, "start_date": start.isoformat(), "end_date": end.isoformat()}
            not in group.terms
        ):
            return False
        snapshot = await db.get(CurriculumSessionSnapshot, key)
        if snapshot is None:
            db.add(
                CurriculumSessionSnapshot(
                    group_id=group_id,
                    semester=semester,
                    start_date=start,
                    end_date=end,
                    attempted_at=attempted,
                )
            )
        elif _due(snapshot.attempted_at, snapshot.checked_at, attempted):
            snapshot.attempted_at = attempted
        else:
            return False
    return True


async def _save_success(key, attempted, checked, lessons):
    async with get_session() as db, db.begin():
        snapshot = await db.get(CurriculumSessionSnapshot, key, with_for_update=True)
        if not snapshot or _utc(snapshot.attempted_at) != attempted:
            return False
        snapshot.checked_at = checked
        snapshot.lessons = [
            {field: row[field] for field in _SOURCE_FIELDS if field in row}
            for row in lessons
            if schedule_assessment_kind(row.get("kindOfWork"))
        ]
    return True


async def refresh_session_dates(http_session, *, now=None) -> dict:
    """Refresh a fair bounded batch of active/near-future reviewed group terms."""
    tick = now or datetime.now(UTC)
    terms = await _due_terms(tick.astimezone(ZoneInfo("Europe/Moscow")).date(), tick)
    client = create_ruz_api_client(http_session, max_retries=1, request_timeout_seconds=12)
    refreshed = failed = 0
    for key in terms:
        attempted = now or datetime.now(UTC)
        try:
            if not await _claim(key, attempted):
                continue
            group, _, start, end = key
            async with asyncio.timeout(13):
                lessons = await client.get_schedule(
                    "group", group, start.isoformat(), end.isoformat()
                )
            if not _valid_schedule(lessons, start, end):
                raise RuzAPIError("Malformed or out-of-range schedule payload")
            if await _save_success(key, attempted, now or datetime.now(UTC), lessons):
                refreshed += 1
        except Exception as exc:
            failed += 1
            logger.warning(
                "Session date refresh failed for group %s, semester %s (%s)",
                key[0],
                key[1],
                type(exc).__name__,
            )
    if refreshed or failed:
        logger.info("Session date refresh finished (refreshed=%s failed=%s)", refreshed, failed)
    return {"refreshed": refreshed, "failed": failed}

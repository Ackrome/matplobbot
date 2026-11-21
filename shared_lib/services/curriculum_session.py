"""Serve assessment dates locally and periodically verify approved semesters with RUZ."""

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from shared_lib.database import get_cached_schedule_with_coverage, get_session
from shared_lib.models import CurriculumDocument, CurriculumGroup, CurriculumSessionSnapshot
from shared_lib.services.curriculum_service import (
    CurriculumConflictError,
    CurriculumNotFoundError,
    match_session_dates,
    read_curriculum_session,
    schedule_assessment_kind,
    session_date_reviews,
)
from shared_lib.services.university_api import RuzAPIError, create_ruz_api_client

logger = logging.getLogger(__name__)
FRESH_FOR = timedelta(hours=6)
RETRY_AFTER = timedelta(hours=1)
LOOKAHEAD = timedelta(days=45)
MAX_TERM_DAYS = 185
MAX_REQUESTS = 8
MAX_DATE_RESOLUTIONS = 1000
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
        "events": match_session_dates(
            assessments,
            lessons,
            first,
            last,
            group_id=group_id,
            resolutions=snapshot.date_resolutions if snapshot and snapshot.checked_at else None,
        ),
    }


async def _review_snapshot(db, group_id, semester, *, lock=False):
    local_day = datetime.now(ZoneInfo("Europe/Moscow")).date()
    plan = await read_curriculum_session(db, group_id, local_day, semester, lock=lock)
    term = plan.get("term")
    if plan["status"] != "confirmed" or term is None:
        raise CurriculumNotFoundError("Approved group semester not found")
    key = _term_key(group_id, term)
    snapshot = await db.get(CurriculumSessionSnapshot, key, with_for_update=lock)
    resolved = snapshot.date_resolutions if snapshot else {}
    reviews = (
        session_date_reviews(
            plan["assessments"],
            snapshot.lessons,
            term["start_date"],
            term["end_date"],
            group_id,
            resolved,
        )
        if snapshot and snapshot.checked_at
        else []
    )
    return plan, snapshot, reviews


async def admin_session_reviews(group_id, semester):
    """Read ambiguous candidates for a single approved group term."""
    async with get_session() as db:
        plan, snapshot, reviews = await _review_snapshot(db, group_id, semester)
        checked = _utc(snapshot.checked_at) if snapshot else None
        return {
            "group_id": plan["group_id"],
            "group_name": plan["group_name"],
            "term": plan["term"],
            "dates_checked_at": checked.isoformat() if checked else None,
            "reviews": reviews,
        }


async def confirm_session_review(
    group_id, term, event_key, review_key, candidate_key, expected_selected
):
    """Match one cached event without changing the publication or timetable."""
    async with get_session() as db, db.begin():
        plan, snapshot, reviews = await _review_snapshot(db, group_id, term["semester"], lock=True)
        selected = next((item for item in reviews if item["event_key"] == event_key), None)
        if (
            plan["term"] != term
            or not snapshot
            or not selected
            or selected["review_key"] != review_key
            or sum(row["candidate_key"] == candidate_key for row in selected["candidates"]) != 1
        ):
            raise CurriculumConflictError("The assessment or timetable changed during review")
        if selected["selected"] == candidate_key:
            return
        if selected["selected"] != expected_selected:
            raise CurriculumConflictError("The date match changed during review")
        resolutions = dict(snapshot.date_resolutions)
        if event_key not in resolutions and len(resolutions) >= MAX_DATE_RESOLUTIONS:
            raise CurriculumConflictError(
                "The group semester has reached the maximum reviewed matches"
            )
        resolutions[event_key] = {"review_key": review_key, "candidate_key": candidate_key}
        snapshot.date_resolutions = resolutions


async def _active_terms(now):
    today = now.astimezone(ZoneInfo("Europe/Moscow")).date()
    horizon = today + LOOKAHEAD
    async with get_session() as db:
        groups = (
            await db.execute(
                select(
                    CurriculumGroup.group_id,
                    CurriculumGroup.group_name,
                    CurriculumGroup.document_id,
                    CurriculumGroup.terms,
                )
                .join(CurriculumDocument, CurriculumDocument.id == CurriculumGroup.document_id)
                .where(
                    CurriculumDocument.published_hash.is_not(None),
                    CurriculumDocument.parent_document_id.is_(None),
                )
                .order_by(CurriculumGroup.group_name, CurriculumGroup.group_id)
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
                    CurriculumSessionSnapshot.last_error,
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
                item.last_error,
            )
            for item in snapshots
        }
    active = []
    for group_id, group_name, document_id, terms in groups:
        for term in sorted(terms, key=lambda item: item["start_date"]):
            key = _term_key(group_id, term)
            start, end = key[2:]
            if not (start <= horizon and end >= today and 0 <= (end - start).days <= MAX_TERM_DAYS):
                continue
            active.append((key, group_name, document_id, term, state.get(key, (None, None, None))))
    return active


async def admin_session_coverage(*, now=None):
    """Report durable scheduler coverage without fetching RUZ or reading lesson bodies."""
    now = now or datetime.now(UTC)
    groups = {}
    for key, group_name, document_id, term, (attempted, checked, error) in await _active_terms(now):
        group_id = key[0]
        if group_id not in groups:
            groups[group_id] = {
                "group_id": group_id,
                "group_name": group_name,
                "document_id": document_id,
                "terms": [],
            }
        stamp = _utc(checked)
        attempted = _utc(attempted)
        verified_at = stamp.isoformat() if stamp else None
        coverage = []
        status = "pending"
        if stamp:
            status = "stale" if now - stamp >= FRESH_FOR else "checked"
            coverage.append(
                {
                    "start_date": term["start_date"],
                    "end_date": term["end_date"],
                    "checked_at": verified_at,
                }
            )
        groups[group_id]["terms"].append(
            {
                **term,
                "dates_status": status,
                "dates_checked_at": verified_at,
                "dates_coverage": coverage,
                "last_attempted_at": attempted.isoformat() if attempted else None,
                "last_error": error,
            }
        )
    return {"groups": list(groups.values())}


async def _due_terms(now):
    choices = []
    for key, _, _, _, (attempted, checked, _) in await _active_terms(now):
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
            snapshot.last_error = None
        else:
            return False
    return True


async def _save_success(key, attempted, checked, lessons):
    async with get_session() as db, db.begin():
        snapshot = await db.get(CurriculumSessionSnapshot, key, with_for_update=True)
        if not snapshot or _utc(snapshot.attempted_at) != attempted:
            return False
        snapshot.checked_at = checked
        snapshot.last_error = None
        snapshot.lessons = [
            {field: row[field] for field in _SOURCE_FIELDS if field in row}
            for row in lessons
            if schedule_assessment_kind(row.get("kindOfWork"))
        ]
    return True


async def _save_failure(key, attempted, code):
    async with get_session() as db, db.begin():
        snapshot = await db.get(CurriculumSessionSnapshot, key, with_for_update=True)
        if snapshot and _utc(snapshot.attempted_at) == attempted:
            snapshot.last_error = code


async def refresh_session_dates(http_session, *, now=None) -> dict:
    """Refresh a fair bounded batch of active/near-future reviewed group terms."""
    tick = now or datetime.now(UTC)
    terms = await _due_terms(tick)
    client = create_ruz_api_client(http_session, max_retries=1, request_timeout_seconds=12)
    refreshed = failed = 0
    for key in terms:
        attempted = now or datetime.now(UTC)
        claimed = False
        error_code = "refresh_failed"
        try:
            claimed = await _claim(key, attempted)
            if not claimed:
                continue
            group, _, start, end = key
            error_code = "upstream_unavailable"
            async with asyncio.timeout(13):
                lessons = await client.get_schedule(
                    "group", group, start.isoformat(), end.isoformat()
                )
            if not _valid_schedule(lessons, start, end):
                error_code = "invalid_response"
                raise RuzAPIError("Malformed or out-of-range schedule payload")
            error_code = "refresh_failed"
            if await _save_success(key, attempted, now or datetime.now(UTC), lessons):
                refreshed += 1
        except Exception as exc:
            failed += 1
            if claimed:
                try:
                    await _save_failure(key, attempted, error_code)
                except Exception as save_error:
                    logger.warning(
                        "Session date failure could not be saved (%s)", type(save_error).__name__
                    )
            logger.warning(
                "Session date refresh failed for group %s, semester %s (%s)",
                key[0],
                key[1],
                type(exc).__name__,
            )
    if refreshed or failed:
        logger.info("Session date refresh finished (refreshed=%s failed=%s)", refreshed, failed)
    return {"refreshed": refreshed, "failed": failed}

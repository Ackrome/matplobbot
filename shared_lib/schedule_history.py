"""Recent verified changes to public university timetables."""

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select

from .database import get_session
from .models import ScheduleHistoryEntry, ScheduleNotificationSnapshot

RETENTION_DAYS = 30
HISTORY_PAGE_SIZE = 50
MAX_TRANSITION_CHANGES = 2000
FIELDS = {
    "date": "date",
    "begin": "beginLesson",
    "end": "endLesson",
    "discipline": "discipline",
    "kind": "kindOfWork",
    "building": "building",
    "room": "auditorium",
    "teacher": "lecturer_title",
    "group": "group",
}


def _public_lesson(lesson: dict) -> dict:
    fields = {key: str(lesson.get(source) or "").strip()[:255] for key, source in FIELDS.items()}
    fields["oid"] = str(lesson.get("lessonOid") or "").strip()[:128]
    fields["teacher"] = fields["teacher"].replace("_", " ")
    fields["date"] = date.fromisoformat(fields["date"]).isoformat()
    for key in ("begin", "end"):
        wall_time = time.fromisoformat(fields[key])
        if wall_time.tzinfo is not None:
            raise ValueError("Unexpected time zone on a university lesson")
        fields[key] = wall_time.isoformat(
            timespec="seconds" if wall_time.second or wall_time.microsecond else "minutes"
        )
    if not fields["discipline"]:
        raise ValueError("Incomplete lesson in schedule response")
    return fields


def _slot(lesson: dict) -> tuple[str, ...]:
    return tuple(lesson[key] for key in ("date", "begin", "end", "group"))


def _pair(outgoing: list[dict], incoming: list[dict], key):
    """Match only when the selected identity is unambiguous on each side."""
    old_by_key = defaultdict(list)
    new_by_key = defaultdict(list)
    for lesson in outgoing:
        old_by_key[key(lesson)].append(lesson)
    for lesson in incoming:
        new_by_key[key(lesson)].append(lesson)
    pairs = []
    for value in old_by_key.keys() & new_by_key.keys():
        if value and len(old_by_key[value]) == len(new_by_key[value]) == 1:
            pairs.append((old_by_key.pop(value)[0], new_by_key.pop(value)[0]))
    return (
        pairs,
        [lesson for group in old_by_key.values() for lesson in group],
        [lesson for group in new_by_key.values() for lesson in group],
    )


def build_schedule_history(
    old: list[dict],
    new: list[dict],
    *,
    semester_start: str,
    semester_end: str,
    today: date | None = None,
) -> list[dict]:
    """Record material future changes without treating a semester rollover as mass cancellation."""
    start, end = (
        date.fromisoformat(semester_start).isoformat(),
        date.fromisoformat(semester_end).isoformat(),
    )
    today_iso = (today or datetime.now(ZoneInfo("Europe/Moscow")).date()).isoformat()

    def relevant(rows):
        unique = {}
        for row in rows:
            lesson = _public_lesson(row)
            if start <= lesson["date"] <= end:
                unique[tuple(lesson.values())] = lesson
        return list(unique.values())

    try:
        before, after = relevant(old), relevant(new)
    except (AttributeError, TypeError, ValueError):
        # A malformed source payload cannot establish a cancellation.
        return []
    if old and not before:  # The previous observation is from another semester.
        return []
    if not before and not after:
        return []
    old_counts = Counter(lesson["oid"] for lesson in before)
    new_counts = Counter(lesson["oid"] for lesson in after)
    _, before, after = _pair(before, after, lambda lesson: tuple(lesson[field] for field in FIELDS))
    pairs, before, after = _pair(before, after, lambda lesson: lesson["oid"])
    # A lesson may be reassigned a source ID. A unique simultaneous slot is
    # enough to call a replacement, but ambiguous parallel lessons stay separate.
    slot_pairs, before, after = _pair(before, after, _slot)
    result = []
    for old_lesson, new_lesson in pairs + slot_pairs:
        fields = [key for key in FIELDS if old_lesson[key] != new_lesson[key]]
        if not fields:
            continue
        kind = "moved" if set(fields) & {"date", "begin", "end"} else "replaced"
        result.append({"kind": kind, "before": old_lesson, "after": new_lesson, "fields": fields})
    result.extend(
        {"kind": "cancelled", "before": lesson, "after": None, "fields": []} for lesson in before
    )
    result.extend(
        {"kind": "added", "before": None, "after": lesson, "fields": []} for lesson in after
    )
    for item in result:
        # Links must not select an arbitrary occurrence of a non-unique source ID.
        for key, counts in (("before", old_counts), ("after", new_counts)):
            lesson = item[key]
            if lesson and counts[lesson["oid"]] > 1:
                item[key] = {**lesson, "oid": ""}
    retained = [
        item
        for item in result
        if any(lesson and lesson["date"] >= today_iso for lesson in (item["before"], item["after"]))
    ]
    return sorted(
        retained,
        key=lambda item: tuple(
            (item["after"] or item["before"])[key]
            for key in ("date", "begin", "group", "discipline", "oid")
        ),
    )[:MAX_TRANSITION_CHANGES]


async def read_schedule_history(
    entity_type: str, entity_id: str, event_key: str | None = None
) -> dict:
    """Return the latest page of public facts, optionally scoped to one poll event."""
    cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
    stmt = select(ScheduleHistoryEntry).where(
        ScheduleHistoryEntry.entity_type == entity_type,
        ScheduleHistoryEntry.entity_id == entity_id,
        ScheduleHistoryEntry.observed_at >= cutoff,
    )
    if event_key:
        stmt = stmt.where(ScheduleHistoryEntry.event_key == event_key)
    stmt = stmt.order_by(
        ScheduleHistoryEntry.observed_at.desc(),
        ScheduleHistoryEntry.event_key,
        ScheduleHistoryEntry.position,
    ).limit(HISTORY_PAGE_SIZE + 1)
    async with get_session() as session:
        result = list((await session.scalars(stmt)).all())
        tracked = bool(result) or bool(
            await session.scalar(
                select(ScheduleNotificationSnapshot.revision).where(
                    ScheduleNotificationSnapshot.entity_type == entity_type,
                    ScheduleNotificationSnapshot.entity_id == entity_id,
                    ScheduleNotificationSnapshot.revision > 1,
                )
            )
        )
        return {
            "items": [
                {
                    "observed_at": row.observed_at.isoformat(),
                    "kind": row.kind,
                    "before": row.before_lesson,
                    "after": row.after_lesson,
                    "fields": row.fields,
                }
                for row in result[:HISTORY_PAGE_SIZE]
            ],
            "truncated": len(result) > HISTORY_PAGE_SIZE,
            "tracked": tracked,
            "retention_days": RETENTION_DAYS,
        }


async def prune_schedule_history() -> int:
    """Delete one bounded indexed batch without touching delivery/outbox rows."""
    cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
    old = (
        select(ScheduleHistoryEntry.id)
        .where(ScheduleHistoryEntry.observed_at < cutoff)
        .order_by(ScheduleHistoryEntry.observed_at, ScheduleHistoryEntry.id)
        .limit(5000)
    )
    async with get_session() as session:
        dropped = await session.execute(
            delete(ScheduleHistoryEntry).where(ScheduleHistoryEntry.id.in_(old))
        )
        await session.commit()
        return dropped.rowcount or 0

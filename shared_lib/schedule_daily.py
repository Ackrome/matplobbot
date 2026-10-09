"""Pure daily-notification occurrence and recipient identity rules."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def daily_occurrence(
    notification_time: time | None,
    timezone_name: str | None,
    now_utc: datetime,
    catchup_seconds: int = 6 * 60 * 60,
) -> dict | None:
    """Find the latest due wall-clock occurrence inside a bounded catch-up window."""
    if notification_time is None:
        return None
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    try:
        timezone = ZoneInfo(timezone_name or "Europe/Moscow")
    except ZoneInfoNotFoundError:
        timezone = ZoneInfo("Europe/Moscow")
    local_now = now_utc.astimezone(timezone)
    scheduled = datetime.combine(local_now.date(), notification_time, timezone)
    if scheduled > local_now:
        scheduled -= timedelta(days=1)
    # Less than 24 hours prevents a single tick from replaying multiple old days.
    window = min(max(60, catchup_seconds), 24 * 60 * 60 - 1)
    age = (now_utc.astimezone(UTC) - scheduled.astimezone(UTC)).total_seconds()
    if not 0 <= age < window:
        return None
    return {
        "scheduled_at": scheduled.astimezone(UTC),
        "target_date": scheduled.date() + timedelta(days=1),
        "expires_at": scheduled.astimezone(UTC) + timedelta(seconds=window),
    }


def daily_event_key(entity_type: str, entity_id: str, target_date: date) -> str:
    """One daily event per entity/source date; the DB unique key adds the user."""
    raw = "\x1f".join(("daily", entity_type, str(entity_id), target_date.isoformat()))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def deduplicate_daily_recipients(subscriptions: list[dict]) -> list[dict]:
    """Choose a deterministic profile for each user/entity/date, preferring private chat."""
    recipients: dict[tuple[int, str, str, date], dict] = {}
    for subscription in sorted(
        subscriptions,
        key=lambda item: (
            int(item.get("chat_id", 0)) != int(item["user_id"]),
            int(item.get("id", 0)),
        ),
    ):
        key = (
            int(subscription["user_id"]),
            subscription["entity_type"],
            str(subscription["entity_id"]),
            subscription["target_date"],
        )
        recipients.setdefault(key, subscription)
    return list(recipients.values())

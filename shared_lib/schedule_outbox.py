"""Durable outbox primitives for schedule-change Telegram notifications."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .database import get_session
from .models import CachedSchedule, ScheduleChangeDelivery, UserScheduleSubscription

OUTBOX_PENDING = "pending"
OUTBOX_PROCESSING = "processing"
OUTBOX_SENT = "sent"
OUTBOX_FAILED = "failed"


async def get_existing_schedule_deliveries(keys: list[tuple[str, int]]) -> set[tuple[str, int]]:
    """Find already persisted daily events without retrieving message contents."""
    if not keys:
        return set()
    from sqlalchemy import tuple_

    existing = set()
    async with get_session() as session:
        for offset in range(0, len(keys), 500):
            rows = await session.execute(
                select(ScheduleChangeDelivery.event_key, ScheduleChangeDelivery.user_id).where(
                    tuple_(ScheduleChangeDelivery.event_key, ScheduleChangeDelivery.user_id).in_(
                        keys[offset : offset + 500]
                    )
                )
            )
            existing.update((row[0], row[1]) for row in rows.all())
    return existing


async def enqueue_daily_schedule_delivery(
    *, event_key: str, subscription: dict, payload: str
) -> int:
    """Persist a daily message before any send; retries keep the original payload."""
    async with get_session() as session:
        result = await session.execute(
            pg_insert(ScheduleChangeDelivery)
            .values(
                event_key=event_key,
                user_id=subscription["user_id"],
                entity_type=subscription["entity_type"],
                entity_id=str(subscription["entity_id"]),
                chat_id=subscription["chat_id"],
                message_thread_id=subscription.get("message_thread_id"),
                payload=payload,
                delivery_kind="daily",
                expires_at=subscription["expires_at"],
            )
            .on_conflict_do_nothing(constraint="uq_schedule_change_delivery_event_user")
        )
        await session.commit()
        return result.rowcount or 0


def build_schedule_change_event_key(
    entity_type: str,
    entity_id: str,
    previous_hash: str,
    new_hash: str,
    source_checked_at: datetime | None,
) -> str:
    """Return a stable key for one observed cache transition.

    Including the previous cache timestamp keeps retries idempotent after an enqueue-before-cache
    crash, while allowing a later A→B transition to notify again after the schedule cycled.
    """
    if source_checked_at is None:
        source_version = previous_hash
    elif source_checked_at.tzinfo is None:
        source_version = source_checked_at.replace(tzinfo=UTC).isoformat()
    else:
        source_version = source_checked_at.astimezone(UTC).isoformat()
    source = "\x1f".join(
        (str(entity_type), str(entity_id), source_version, str(previous_hash), str(new_hash))
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


async def enqueue_schedule_change_deliveries(
    event_key: str,
    entity_type: str,
    entity_id: str,
    deliveries: list[dict[str, Any]],
) -> int:
    """Insert one pending delivery per application user, ignoring exact retry duplicates."""
    if not deliveries:
        return 0

    rows = [
        {
            "event_key": event_key,
            "user_id": int(item["user_id"]),
            "entity_type": str(entity_type),
            "entity_id": str(entity_id),
            "chat_id": int(item["chat_id"]),
            "message_thread_id": item.get("message_thread_id"),
            "payload": str(item["payload"]),
            "status": OUTBOX_PENDING,
        }
        for item in deliveries
    ]
    async with get_session() as session:
        result = await session.execute(
            pg_insert(ScheduleChangeDelivery)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_schedule_change_delivery_event_user")
        )
        await session.commit()
        return result.rowcount or 0


async def commit_schedule_change_transition(
    *,
    event_key: str,
    entity_type: str,
    entity_id: str,
    entity_name: str,
    schedule_data: list | dict,
    new_hash: str,
    deliveries: list[dict[str, Any]],
) -> int:
    """Atomically persist the outbox rows and advance cache/subscription checkpoints."""
    normalized_entity_id = str(entity_id)
    normalized_schedule = json.loads(json.dumps(schedule_data, default=str))
    rows = [
        {
            "event_key": event_key,
            "user_id": int(item["user_id"]),
            "entity_type": str(entity_type),
            "entity_id": normalized_entity_id,
            "chat_id": int(item["chat_id"]),
            "message_thread_id": item.get("message_thread_id"),
            "payload": str(item["payload"]),
            "status": OUTBOX_PENDING,
        }
        for item in deliveries
    ]
    now = datetime.now(UTC)

    async with get_session() as session:
        inserted = 0
        if rows:
            result = await session.execute(
                pg_insert(ScheduleChangeDelivery)
                .values(rows)
                .on_conflict_do_nothing(constraint="uq_schedule_change_delivery_event_user")
            )
            inserted = result.rowcount or 0

        await session.execute(
            pg_insert(CachedSchedule)
            .values(
                entity_type=entity_type,
                entity_id=normalized_entity_id,
                entity_name=str(entity_name)[:255],
                schedule_data=normalized_schedule,
                updated_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_cached_schedule_entity",
                set_={
                    "entity_name": str(entity_name)[:255],
                    "schedule_data": normalized_schedule,
                    "updated_at": now,
                },
            )
        )
        await session.execute(
            update(UserScheduleSubscription)
            .where(
                UserScheduleSubscription.entity_type == entity_type,
                UserScheduleSubscription.entity_id == normalized_entity_id,
                UserScheduleSubscription.is_active.is_(True),
            )
            .values(last_schedule_hash=new_hash)
        )
        await session.commit()
        return inserted


async def claim_schedule_change_deliveries(
    *,
    limit: int = 100,
    max_attempts: int = 8,
    lock_timeout_seconds: int = 900,
    now_utc: datetime | None = None,
) -> list[dict[str, Any]]:
    """Atomically claim ready rows and reclaim abandoned processing rows."""
    now = now_utc or datetime.now(UTC)
    stale_before = now - timedelta(seconds=max(1, lock_timeout_seconds))
    async with get_session() as session:
        # A worker can crash after claiming its final attempt. Such rows must leave
        # processing even though they are no longer eligible for another claim.
        abandoned = and_(
            ScheduleChangeDelivery.status == OUTBOX_PROCESSING,
            or_(
                ScheduleChangeDelivery.locked_at.is_(None),
                ScheduleChangeDelivery.locked_at <= stale_before,
            ),
        )
        ready_or_abandoned = or_(ScheduleChangeDelivery.status == OUTBOX_PENDING, abandoned)
        await session.execute(
            update(ScheduleChangeDelivery)
            .where(
                ready_or_abandoned,
                or_(
                    ScheduleChangeDelivery.attempt_count >= max_attempts,
                    ScheduleChangeDelivery.expires_at <= now,
                ),
            )
            .values(
                status=OUTBOX_FAILED,
                locked_at=None,
                updated_at=now,
                last_error="Delivery window or attempt budget exhausted; delivery may be unconfirmed",
            )
        )
        result = await session.execute(
            select(ScheduleChangeDelivery)
            .where(
                ScheduleChangeDelivery.attempt_count < max_attempts,
                or_(
                    ScheduleChangeDelivery.expires_at.is_(None),
                    ScheduleChangeDelivery.expires_at > now,
                ),
                or_(
                    and_(
                        ScheduleChangeDelivery.status == OUTBOX_PENDING,
                        ScheduleChangeDelivery.next_attempt_at <= now,
                    ),
                    and_(
                        ScheduleChangeDelivery.status == OUTBOX_PROCESSING,
                        or_(
                            ScheduleChangeDelivery.locked_at.is_(None),
                            ScheduleChangeDelivery.locked_at <= stale_before,
                        ),
                    ),
                ),
            )
            .order_by(ScheduleChangeDelivery.created_at, ScheduleChangeDelivery.id)
            .limit(max(1, limit))
            .with_for_update(skip_locked=True)
        )
        rows = list(result.scalars().all())
        claimed: list[dict[str, Any]] = []
        for row in rows:
            row.status = OUTBOX_PROCESSING
            row.locked_at = now
            row.updated_at = now
            row.attempt_count = int(row.attempt_count or 0) + 1
            claimed.append(
                {
                    "id": row.id,
                    "event_key": row.event_key,
                    "user_id": row.user_id,
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "chat_id": row.chat_id,
                    "message_thread_id": row.message_thread_id,
                    "payload": row.payload,
                    "attempt_count": row.attempt_count,
                    "delivery_kind": row.delivery_kind,
                }
            )
        await session.commit()
        return claimed


async def mark_schedule_change_delivery_sent(
    delivery_id: int,
    *,
    now_utc: datetime | None = None,
    expected_attempt_count: int | None = None,
) -> None:
    now = now_utc or datetime.now(UTC)
    async with get_session() as session:
        statement = update(ScheduleChangeDelivery).where(ScheduleChangeDelivery.id == delivery_id)
        if expected_attempt_count is not None:
            statement = statement.where(
                ScheduleChangeDelivery.status == OUTBOX_PROCESSING,
                ScheduleChangeDelivery.attempt_count == expected_attempt_count,
            )
        await session.execute(
            statement.values(
                status=OUTBOX_SENT,
                sent_at=now,
                locked_at=None,
                last_error=None,
                updated_at=now,
            )
        )
        await session.commit()


async def reschedule_schedule_change_delivery(
    delivery_id: int,
    *,
    error: str,
    delay_seconds: float,
    terminal: bool = False,
    now_utc: datetime | None = None,
    expected_attempt_count: int | None = None,
) -> None:
    now = now_utc or datetime.now(UTC)
    next_attempt_at = now + timedelta(seconds=max(0.0, delay_seconds))
    async with get_session() as session:
        statement = update(ScheduleChangeDelivery).where(ScheduleChangeDelivery.id == delivery_id)
        if expected_attempt_count is not None:
            statement = statement.where(
                ScheduleChangeDelivery.status == OUTBOX_PROCESSING,
                ScheduleChangeDelivery.attempt_count == expected_attempt_count,
            )
        await session.execute(
            statement.values(
                status=OUTBOX_FAILED if terminal else OUTBOX_PENDING,
                next_attempt_at=next_attempt_at,
                locked_at=None,
                last_error=str(error)[:2000],
                updated_at=now,
            )
        )
        await session.commit()


async def get_schedule_outbox_health(now_utc: datetime | None = None) -> dict:
    """Low-cardinality operational counters, without recipient or message data."""
    now = now_utc or datetime.now(UTC)
    async with get_session() as session:
        result = await session.execute(
            select(
                ScheduleChangeDelivery.status,
                func.count(),
                func.min(ScheduleChangeDelivery.created_at),
            )
            .where(ScheduleChangeDelivery.status != OUTBOX_SENT)
            .group_by(ScheduleChangeDelivery.status)
        )
        counts = {OUTBOX_PENDING: 0, OUTBOX_PROCESSING: 0, OUTBOX_FAILED: 0}
        oldest = None
        for status, count, created_at in result.all():
            counts[status] = int(count)
            if status in {OUTBOX_PENDING, OUTBOX_PROCESSING} and created_at is not None:
                aware = created_at.replace(tzinfo=UTC) if created_at.tzinfo is None else created_at
                oldest = min(oldest, aware) if oldest is not None else aware
    return {
        **counts,
        "oldest_pending_age_seconds": max(0, int((now - oldest).total_seconds())) if oldest else 0,
    }

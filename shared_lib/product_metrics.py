"""Content-free, best-effort product outcomes with account-scoped erasure."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import String, case, cast, delete, func, select
from sqlalchemy.dialects.postgresql import insert

from .database import get_session
from .models import ProductEvent, WebAccount

logger = logging.getLogger(__name__)
EVENT_NAMES = frozenset(
    {
        "search_started",
        "search_succeeded",
        "search_empty",
        "search_failed",
        "subscription_created",
        "studio_started",
        "studio_succeeded",
        "studio_failed",
    }
)
RETENTION_DAYS = 90


async def record_product_event(
    event_name: str,
    *,
    web_account_id: int | None = None,
    telegram_user_id: int | None = None,
    dedupe_key: str | None = None,
) -> None:
    """Record an allowlisted outcome, never query text, documents, names or credentials."""
    if event_name not in EVENT_NAMES:
        raise ValueError("Unknown product event")
    if (web_account_id is None) == (telegram_user_id is None):
        raise ValueError("Exactly one account identity is required")
    try:
        async with asyncio.timeout(2):
            async with get_session() as session:
                if web_account_id is not None:
                    linked_id = await session.scalar(
                        select(WebAccount.telegram_id).where(WebAccount.id == web_account_id)
                    )
                    if linked_id is not None:
                        telegram_user_id, web_account_id = linked_id, None
                if event_name == "subscription_created":
                    actor = (
                        f"tg:{telegram_user_id}" if telegram_user_id else f"web:{web_account_id}"
                    )
                    dedupe_key = f"subscription-created:{actor}"
                await session.execute(
                    insert(ProductEvent)
                    .values(
                        event_name=event_name,
                        web_account_id=web_account_id,
                        telegram_user_id=telegram_user_id,
                        dedupe_key=dedupe_key,
                    )
                    .on_conflict_do_nothing()
                )
                await session.commit()
    except Exception as exc:
        logger.warning("Product metric unavailable (%s)", type(exc).__name__)


async def purge_expired_product_events() -> None:
    """Delete only this feature's telemetry after its documented retention period."""
    async with get_session() as session:
        await session.execute(
            delete(ProductEvent).where(
                ProductEvent.created_at < datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
            )
        )
        await session.commit()


async def get_product_snapshot(session, days: int = 30) -> dict:
    """Aggregate outcomes and users returning on a different UTC day, no raw events."""
    if not 1 <= days <= RETENTION_DAYS:
        raise ValueError("Invalid metrics period")
    since = datetime.now(UTC) - timedelta(days=days)
    condition = ProductEvent.created_at >= since
    counts = dict(
        (
            await session.execute(
                select(ProductEvent.event_name, func.count())
                .where(condition)
                .group_by(ProductEvent.event_name)
            )
        ).all()
    )
    counts = {name: int(counts.get(name, 0)) for name in sorted(EVENT_NAMES)}
    # Link historical web events at read time too: otherwise one person who
    # links Telegram after their first day is counted as two non-returning actors.
    joined_accounts = ProductEvent.__table__.outerjoin(
        WebAccount.__table__, ProductEvent.web_account_id == WebAccount.id
    )
    canonical_telegram_id = func.coalesce(ProductEvent.telegram_user_id, WebAccount.telegram_id)
    actor = case(
        (
            canonical_telegram_id.is_not(None),
            "tg:" + cast(canonical_telegram_id, String),
        ),
        else_="web:" + cast(ProductEvent.web_account_id, String),
    )
    day = func.date(func.timezone("UTC", ProductEvent.created_at))
    counts["subscription_created"] = int(
        (
            await session.execute(
                select(func.count(func.distinct(actor)))
                .select_from(joined_accounts)
                .where(condition, ProductEvent.event_name == "subscription_created")
            )
        ).scalar_one()
    )
    users = (
        select(actor.label("actor"), func.count(func.distinct(day)).label("days"))
        .select_from(joined_accounts)
        .where(condition)
        .group_by(actor)
        .subquery()
    )
    active, returning = (
        await session.execute(
            select(func.count(), func.count().filter(users.c.days >= 2)).select_from(users)
        )
    ).one()
    daily_rows = (
        await session.execute(
            select(day, func.count(), func.count(func.distinct(actor)))
            .select_from(joined_accounts)
            .where(condition)
            .group_by(day)
            .order_by(day)
        )
    ).all()
    completed_searches = sum(
        counts[name] for name in ("search_succeeded", "search_empty", "search_failed")
    )
    return {
        "days": days,
        "since": since.isoformat(),
        "timezone": "UTC",
        "retention_days": RETENTION_DAYS,
        "counts": counts,
        "active_users": int(active or 0),
        "returning_users": int(returning or 0),
        "search_success_rate": (
            round(counts["search_succeeded"] / completed_searches, 4)
            if completed_searches
            else None
        ),
        "daily": [
            {"date": str(date), "events": count, "active_users": users}
            for date, count, users in daily_rows
        ],
        "definitions": {
            "search_success": "A completed global search with at least one result",
            "subscription_created": "Distinct canonical accounts with a subscription-created event in this period",
            "returning_users": "Accounts with events on at least two distinct UTC dates in this period",
            "studio_succeeded": "Successful asynchronous compile result retrieved by its owner",
        },
    }

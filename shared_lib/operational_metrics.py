"""Bounded Redis heartbeats for useful work, without message content or identities."""

import asyncio
import logging
import math
from datetime import UTC, datetime

import redis

from .redis_client import get_redis_url, redis_client

logger = logging.getLogger(__name__)
OPERATIONS = {
    "daily_schedules": 3 * 60,
    "schedule_refresh": 13 * 3600,
    "schedule_updates": 3 * 3600,
    "outbox_delivery": 5 * 60,
    "studio_compile": None,
}
PREFIX = "mpb:operations:"
RETENTION_SECONDS = 7 * 86400


def _fields(successful: bool, duration_seconds: float, error_code: str | None):
    now = datetime.now(UTC).isoformat()
    duration = max(0.0, float(duration_seconds))
    if not math.isfinite(duration):
        duration = 0.0
    fields = {
        "last_attempt": now,
        "last_duration_seconds": round(duration, 3),
        "last_status": "success" if successful else "error",
    }
    fields["last_success" if successful else "last_failure"] = now
    # Caller passes a symbolic code, never exception text / user payload.
    fields["last_error_code"] = "" if successful else (error_code or "operation_failed")[:64]
    return fields


async def record_operation(
    name: str,
    *,
    successful: bool,
    duration_seconds: float,
    error_code: str | None = None,
) -> None:
    if name not in OPERATIONS:
        raise ValueError("Unknown operation")
    try:
        async with asyncio.timeout(2):
            async with redis_client.client.pipeline(transaction=True) as pipe:
                pipe.hset(PREFIX + name, mapping=_fields(successful, duration_seconds, error_code))
                pipe.hincrby(PREFIX + name, "successes" if successful else "failures", 1)
                pipe.expire(PREFIX + name, RETENTION_SECONDS)
                await pipe.execute()
    except Exception as exc:
        logger.warning("Operational heartbeat unavailable (%s)", type(exc).__name__)


def record_operation_sync(
    name: str,
    *,
    successful: bool,
    duration_seconds: float,
    error_code: str | None = None,
) -> None:
    """Worker-safe counterpart; no asyncio/database session is shared across forks."""
    if name not in OPERATIONS:
        raise ValueError("Unknown operation")
    try:
        with redis.Redis.from_url(
            get_redis_url(),
            socket_connect_timeout=1,
            socket_timeout=1,
            decode_responses=True,
        ) as client:
            with client.pipeline(transaction=True) as pipe:
                pipe.hset(PREFIX + name, mapping=_fields(successful, duration_seconds, error_code))
                pipe.hincrby(PREFIX + name, "successes" if successful else "failures", 1)
                pipe.expire(PREFIX + name, RETENTION_SECONDS)
                pipe.execute()
    except Exception as exc:
        logger.warning("Worker heartbeat unavailable (%s)", type(exc).__name__)


async def get_operational_snapshot() -> dict:
    now = datetime.now(UTC)
    try:
        async with asyncio.timeout(2):
            async with redis_client.client.pipeline(transaction=False) as pipe:
                for name in OPERATIONS:
                    pipe.hgetall(PREFIX + name)
                rows = await pipe.execute()
    except Exception:
        return {"available": False, "checked_at": now.isoformat(), "operations": []}
    operations = []
    for (name, threshold), row in zip(OPERATIONS.items(), rows, strict=True):
        row = dict(row or {})
        age = None
        if row.get("last_success"):
            try:
                age = max(0, (now - datetime.fromisoformat(row["last_success"])).total_seconds())
            except (ValueError, TypeError):
                pass
        status = "unknown" if not row else row.get("last_status", "unknown")
        if threshold and age is not None and age > threshold:
            status = "stale"
        operations.append(
            {
                "name": name,
                **row,
                "status": status,
                "success_age_seconds": age,
                "stale_after_seconds": threshold,
            }
        )
    return {"available": True, "checked_at": now.isoformat(), "operations": operations}

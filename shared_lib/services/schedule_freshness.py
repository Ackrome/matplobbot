"""Stale-while-revalidate schedule loading with per-entity request coalescing."""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

from shared_lib.database import get_cached_schedule_snapshot, upsert_cached_schedule
from shared_lib.redis_client import redis_client
from shared_lib.services.schedule_service import (
    get_semester_bounds,
    record_schedule_fallback_metric,
)

logger = logging.getLogger(__name__)

FreshnessState = Literal["live", "fresh_cache", "refreshing", "stale_fallback"]
_LOCK_PREFIX = "schedule_refresh_lock:"
_FAILURE_PREFIX = "schedule_refresh_failure:"
_REDIS_OPERATION_TIMEOUT_SECONDS = 0.3
_RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


class ScheduleUnavailableError(RuntimeError):
    """Raised when neither cached nor live schedule data is available."""


@dataclass(frozen=True, slots=True)
class ScheduleFreshnessResult:
    schedule: list[dict]
    freshness: FreshnessState
    source_checked_at: datetime | None
    refresh_in_progress: bool
    cache_age_seconds: int | None
    content_changed: bool = False

    @property
    def is_offline(self) -> bool:
        return self.freshness == "stale_fallback"


@dataclass(frozen=True, slots=True)
class _RefreshOutcome:
    status: Literal["success", "failed", "coalesced"]
    schedule: list[dict] | None = None
    source_checked_at: datetime | None = None
    content_changed: bool = False


_refresh_tasks: dict[str, asyncio.Task[_RefreshOutcome]] = {}
_metric_tasks: set[asyncio.Task[None]] = set()
_local_failure_until: dict[str, float] = {}


def _entity_key(entity_type: str, entity_id: str) -> str:
    return f"{entity_type}:{entity_id}"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _cache_age_seconds(value: datetime | None) -> int | None:
    normalized = _as_utc(value)
    if normalized is None:
        return None
    return max(0, int((datetime.now(UTC) - normalized).total_seconds()))


def _forget_metric_task(task: asyncio.Task[None]) -> None:
    _metric_tasks.discard(task)
    if not task.cancelled():
        task.exception()


def _record_refresh_metric(outcome: str) -> None:
    """Record telemetry off the response path so Redis cannot delay page loads."""

    task = asyncio.create_task(
        record_schedule_fallback_metric(outcome),
        name=f"schedule-refresh-metric:{outcome}",
    )
    _metric_tasks.add(task)
    task.add_done_callback(_forget_metric_task)


def _filter_schedule_window(schedule: list[dict], start: str, end: str) -> list[dict]:
    requested_start = date.fromisoformat(start)
    requested_end = date.fromisoformat(end)
    filtered: list[dict] = []
    for lesson in schedule:
        lesson_date_value = str(lesson.get("date") or "").replace(".", "-")
        try:
            lesson_date = date.fromisoformat(lesson_date_value)
        except ValueError:
            continue
        if requested_start <= lesson_date <= requested_end:
            filtered.append(lesson)
    return filtered


async def _acquire_distributed_lock(key: str, ttl_seconds: int) -> str | None | bool:
    """Return token when acquired, False when held elsewhere, or None if Redis failed."""

    token = secrets.token_urlsafe(18)
    try:
        acquired = await asyncio.wait_for(
            redis_client.client.set(
                f"{_LOCK_PREFIX}{key}",
                token,
                nx=True,
                ex=ttl_seconds,
            ),
            timeout=_REDIS_OPERATION_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning("Schedule refresh Redis lease unavailable for %s: %s", key, exc)
        return None
    return token if acquired else False


async def _release_distributed_lock(key: str, token: str) -> None:
    try:
        await asyncio.wait_for(
            redis_client.client.eval(
                _RELEASE_LOCK_SCRIPT,
                1,
                f"{_LOCK_PREFIX}{key}",
                token,
            ),
            timeout=_REDIS_OPERATION_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning("Could not release schedule refresh Redis lease for %s: %s", key, exc)


async def _failure_cooldown_active(key: str) -> bool:
    if _local_failure_until.get(key, 0.0) > time.monotonic():
        return True
    try:
        return bool(
            await asyncio.wait_for(
                redis_client.client.exists(f"{_FAILURE_PREFIX}{key}"),
                timeout=_REDIS_OPERATION_TIMEOUT_SECONDS,
            )
        )
    except Exception:
        return False


async def _mark_refresh_failure(key: str, cooldown_seconds: int) -> None:
    _local_failure_until[key] = time.monotonic() + cooldown_seconds
    try:
        await asyncio.wait_for(
            redis_client.client.set(
                f"{_FAILURE_PREFIX}{key}",
                "1",
                ex=cooldown_seconds,
            ),
            timeout=_REDIS_OPERATION_TIMEOUT_SECONDS,
        )
    except Exception:
        return


async def _clear_refresh_failure(key: str) -> None:
    _local_failure_until.pop(key, None)
    try:
        await asyncio.wait_for(
            redis_client.client.delete(f"{_FAILURE_PREFIX}{key}"),
            timeout=_REDIS_OPERATION_TIMEOUT_SECONDS,
        )
    except Exception:
        return


async def _refresh_schedule(
    ruz_api_client,
    entity_type: str,
    entity_id: str,
    cached_schedule: list[dict] | None,
    *,
    lock_ttl_seconds: int,
    failure_cooldown_seconds: int,
) -> _RefreshOutcome:
    key = _entity_key(entity_type, entity_id)
    lock_token = await _acquire_distributed_lock(key, lock_ttl_seconds)
    if lock_token is False:
        return _RefreshOutcome(status="coalesced")

    try:
        semester_start, semester_end = get_semester_bounds()
        schedule = await ruz_api_client.get_schedule(
            entity_type,
            entity_id,
            start=semester_start,
            finish=semester_end,
        )
        if not isinstance(schedule, list):
            raise TypeError("University schedule response must be a list")

        content_changed = cached_schedule is None or cached_schedule != schedule
        await upsert_cached_schedule(entity_type, entity_id, schedule)
        _, source_checked_at = await get_cached_schedule_snapshot(entity_type, entity_id)
        await _clear_refresh_failure(key)
        _record_refresh_metric("ruz_api_success")
        logger.info(
            "Schedule source verified for %s (lessons=%s changed=%s)",
            key,
            len(schedule),
            content_changed,
        )
        return _RefreshOutcome(
            status="success",
            schedule=schedule,
            source_checked_at=_as_utc(source_checked_at) or datetime.now(UTC),
            content_changed=content_changed,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        await _mark_refresh_failure(key, failure_cooldown_seconds)
        _record_refresh_metric("cache_fallback" if cached_schedule is not None else "no_cache")
        logger.warning("Schedule live refresh failed for %s: %s", key, exc)
        return _RefreshOutcome(status="failed")
    finally:
        if isinstance(lock_token, str):
            await _release_distributed_lock(key, lock_token)


def _forget_refresh_task(key: str, task: asyncio.Task[_RefreshOutcome]) -> None:
    if _refresh_tasks.get(key) is task:
        _refresh_tasks.pop(key, None)
    if not task.cancelled():
        task.exception()


def _get_or_start_refresh_task(
    ruz_api_client,
    entity_type: str,
    entity_id: str,
    cached_schedule: list[dict] | None,
    *,
    lock_ttl_seconds: int,
    failure_cooldown_seconds: int,
) -> asyncio.Task[_RefreshOutcome]:
    key = _entity_key(entity_type, entity_id)
    task = _refresh_tasks.get(key)
    if task and not task.done():
        return task

    task = asyncio.create_task(
        _refresh_schedule(
            ruz_api_client,
            entity_type,
            entity_id,
            cached_schedule,
            lock_ttl_seconds=lock_ttl_seconds,
            failure_cooldown_seconds=failure_cooldown_seconds,
        ),
        name=f"schedule-refresh:{key}",
    )
    _refresh_tasks[key] = task
    task.add_done_callback(lambda completed: _forget_refresh_task(key, completed))
    return task


def _build_result(
    schedule: list[dict],
    freshness: FreshnessState,
    source_checked_at: datetime | None,
    requested_start: str,
    requested_end: str,
    *,
    refresh_in_progress: bool,
    content_changed: bool = False,
) -> ScheduleFreshnessResult:
    return ScheduleFreshnessResult(
        schedule=_filter_schedule_window(schedule, requested_start, requested_end),
        freshness=freshness,
        source_checked_at=_as_utc(source_checked_at),
        refresh_in_progress=refresh_in_progress,
        cache_age_seconds=_cache_age_seconds(source_checked_at),
        content_changed=content_changed,
    )


async def get_schedule_with_freshness(
    ruz_api_client,
    entity_type: str,
    entity_id: str,
    requested_start: str,
    requested_end: str,
    *,
    freshness_seconds: int,
    live_wait_seconds: float,
    initial_live_wait_seconds: float,
    lock_ttl_seconds: int,
    failure_cooldown_seconds: int,
    force_refresh: bool = False,
) -> ScheduleFreshnessResult:
    """Return cached data immediately while coalescing a live refresh when needed."""

    cached_payload, source_checked_at = await get_cached_schedule_snapshot(entity_type, entity_id)
    cached_schedule = cached_payload if isinstance(cached_payload, list) else None
    has_cache = cached_schedule is not None
    cache_age_seconds = _cache_age_seconds(source_checked_at)

    if (
        has_cache
        and not force_refresh
        and cache_age_seconds is not None
        and cache_age_seconds <= freshness_seconds
    ):
        return _build_result(
            cached_schedule,
            "fresh_cache",
            source_checked_at,
            requested_start,
            requested_end,
            refresh_in_progress=False,
        )

    key = _entity_key(entity_type, entity_id)
    if not force_refresh and await _failure_cooldown_active(key):
        if has_cache:
            return _build_result(
                cached_schedule,
                "stale_fallback",
                source_checked_at,
                requested_start,
                requested_end,
                refresh_in_progress=False,
            )
        raise ScheduleUnavailableError(
            "University schedule is temporarily unavailable and no cached copy exists."
        )

    task = _get_or_start_refresh_task(
        ruz_api_client,
        entity_type,
        entity_id,
        cached_schedule,
        lock_ttl_seconds=lock_ttl_seconds,
        failure_cooldown_seconds=failure_cooldown_seconds,
    )
    wait_seconds = initial_live_wait_seconds if not has_cache else live_wait_seconds
    try:
        outcome = await asyncio.wait_for(asyncio.shield(task), timeout=wait_seconds)
    except TimeoutError:
        if has_cache:
            return _build_result(
                cached_schedule,
                "refreshing",
                source_checked_at,
                requested_start,
                requested_end,
                refresh_in_progress=True,
            )
        raise ScheduleUnavailableError(
            "University schedule is taking too long to respond and no cached copy exists."
        ) from None

    if outcome.status == "success" and outcome.schedule is not None:
        return _build_result(
            outcome.schedule,
            "live",
            outcome.source_checked_at,
            requested_start,
            requested_end,
            refresh_in_progress=False,
            content_changed=outcome.content_changed,
        )

    if outcome.status == "coalesced":
        if has_cache:
            return _build_result(
                cached_schedule,
                "refreshing",
                source_checked_at,
                requested_start,
                requested_end,
                refresh_in_progress=True,
            )
        deadline = time.monotonic() + initial_live_wait_seconds
        while time.monotonic() < deadline:
            await asyncio.sleep(0.2)
            refreshed_payload, refreshed_at = await get_cached_schedule_snapshot(
                entity_type, entity_id
            )
            if isinstance(refreshed_payload, list):
                return _build_result(
                    refreshed_payload,
                    "live",
                    refreshed_at,
                    requested_start,
                    requested_end,
                    refresh_in_progress=False,
                )

    if has_cache:
        return _build_result(
            cached_schedule,
            "stale_fallback",
            source_checked_at,
            requested_start,
            requested_end,
            refresh_in_progress=False,
        )
    raise ScheduleUnavailableError("University schedule is unavailable and no cached copy exists.")


async def shutdown_schedule_refresh_tasks() -> None:
    """Cancel opportunistic refreshes during API shutdown."""

    tasks = [task for task in [*_refresh_tasks.values(), *_metric_tasks] if not task.done()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _refresh_tasks.clear()
    _metric_tasks.clear()


def reset_schedule_refresh_state_for_tests() -> None:
    """Clear process-local cooldown state after isolated unit tests."""

    _local_failure_until.clear()
    _refresh_tasks.clear()
    _metric_tasks.clear()

# `schedule_freshness.py`

## Purpose

Loads website schedules with stale-while-revalidate semantics. A recently verified entity cache is returned immediately; old data triggers one coalesced full-semester RUZ refresh instead of one upstream request per viewer.

## Public API

- `get_schedule_with_freshness(...)` returns `ScheduleFreshnessResult` with the filtered date window, freshness state, last successful source-check time, refresh flag, cache age, and whether live content changed.
- `ScheduleUnavailableError` signals that both live RUZ data and a cached copy are unavailable.
- `shutdown_schedule_refresh_tasks()` cancels opportunistic background work during API shutdown.
- `reset_schedule_refresh_state_for_tests()` clears process-local task/cooldown bookkeeping in isolated tests.

Freshness states are:

- `live`: this request received and stored a successful RUZ response;
- `fresh_cache`: a recently verified shared entity cache was sufficient;
- `refreshing`: cached data was returned while another refresh continues;
- `stale_fallback`: the latest refresh failed and cached data is being served during a short cooldown.

## Usage

The schedule API passes its configured freshness TTL, wait budgets, Redis lease TTL, and failure cooldown. It keeps the compatibility `is_offline` flag while exposing the more precise state to the frontend.

## Dependencies and side effects

Uses PostgreSQL `cached_schedules` as the shared schedule snapshot, the existing RUZ client for source reads, and Redis for cross-process leases and failure cooldowns. A local task registry also coalesces requests within one API process. Source-outcome metrics run outside the response path and have a bounded Redis timeout. Successful empty lists are authoritative and replace older lessons; malformed non-list payloads fail without overwriting cache.

## Maintenance notes

Keep Redis lease release token-safe. Never await a background refresh with an unshielded timeout, because that would cancel the shared request for all viewers. When changing state names, update the response schema, frontend localization, tests, and this document together.

# `myschedule_filters.py`

## Purpose

Owns persistence, Redis caching, legacy-cache migration, active-subscription lookup, and built-in presets for the aggregated “My schedule” filters. It is extracted from `ScheduleManager` so handler routing and filter state can evolve independently.

## Public API

`MyScheduleFilterService` exposes `get`, `save`, `get_active_subscriptions`, and `build_builtin`.

## Usage

`ScheduleManager` creates one service and keeps its former private methods as compatibility facades. New schedule handlers should call the service directly when they do not need the manager facade.

## Dependencies and side effects

The service reads and writes PostgreSQL through `bot.database` and mirrors normalized filters into the shared Redis client for one hour. Reading may migrate a non-empty legacy Redis value into an empty database record.

## Maintenance

Keep allowed lesson types synchronized with `shared_lib.database.MYSCHEDULE_FILTER_ALLOWED_TYPES`. Preserve the database-first behavior and facade methods while older handlers or tests rely on them.

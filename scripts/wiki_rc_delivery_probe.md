# `rc_delivery_probe.py`

## Purpose

Tests PostgreSQL delivery transaction behavior inside the disposable release candidate
network. SQLite unit tests cannot establish `FOR UPDATE SKIP LOCKED` behavior.

## Public function and usage

`await verify_delivery_concurrency()` returns compact pass flags. Invoke it from
`rc_probe.py` after `init_db_pool()` and the ordinary outbox retry journey, before
`close_db_pool()`. It requires `MPB_ISOLATED_RC=1`, the harness's synthetic user
910000002, and unused `rc-delivery-*` entity IDs. It has no standalone CLI.

The probe holds one real row lock while a second connection claims another row;
races two snapshot updates at one revision; forces a foreign-key enqueue failure
after a snapshot update; and deletes/pauses overlapping subscription profiles
before checking delivery eligibility. Each PostgreSQL lock/race wait is bounded.

## Dependencies and side effects

Uses the initialized application SQLAlchemy pool, database subscription APIs, and
outbox APIs. It inserts synthetic profiles, snapshots, caches and delivery rows in
the disposable database. Successful synthetic claims are directly acknowledged
without Telegram requests. The parent harness owns database/container teardown.

## Maintenance notes

Never run against a production database. Keep the entity namespace separate from
the ordinary retry fixture. A second invocation intentionally fails rather than
modifying prior fixture state. The test needs a PostgreSQL pool with more than one
connection and the migration containing `schedule_notification_snapshots` applied.

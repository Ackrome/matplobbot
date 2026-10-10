# Delivery and scheduler-health regression tests

`test_schedule_delivery.py` tests `daily_occurrence` timezone/catch-up rules,
date-based dedupe, recovery after the final outbox attempt crashes, expiry,
attempt-count fencing and operational health semantics. Outbox transition tests
execute real SQLAlchemy queries against isolated in-memory SQLite tables,
using an async adapter around synchronous sessions; they require no live DB,
Redis, Telegram account or credentials.

Run: `.venv/Scripts/python.exe -m unittest tests.test_schedule_delivery`.
Dependencies: unittest, SQLAlchemy and application helpers. Side effects are
limited to disposable memory databases and mocked operational services.
SQLite does not establish PostgreSQL `SKIP LOCKED` concurrency semantics; keep
that guarantee in the production query and add integration coverage when
changing transaction/locking behavior. Test final-attempt stale claims
separately from claims that still have a retry budget.

The suite also executes the real cache writer and notification scanner twice to
prove an intervening refresh does not consume a change. Real SQLite transactions
exercise baseline revision conflicts and rollback after an injected outbox write
failure, a competing baseline commit while a slow source reply is pending,
subscription pause/delete after claim, overlapping profiles, exact chat
eligibility, recent failures aging out, bounded retention and migration backfill /
downgrade. Table copies adapt JSONB and generated bigint IDs to SQLite without
modifying production model metadata. Network sends remain mocked.

`_sqlite_statement` explicitly translates named PostgreSQL unique constraints to
SQLite conflict-column targets on copied statement/clause objects. It rejects
unknown names and preserves the original PostgreSQL statement. This adaptation
is necessary across SQLAlchemy versions: the pinned 2.0.35 compiler interpreted
the constraint name as a SQLite column, while 2.0.48 omitted the target. Keep the
regression for both DO UPDATE and DO NOTHING and test with the repository pin.
This test-only helper uses SQLAlchemy statement internals; review it when changing
that dependency. Production PostgreSQL queries remain unchanged.

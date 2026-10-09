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

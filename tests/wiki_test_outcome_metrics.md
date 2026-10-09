# Outcome metrics regression tests

`test_outcome_metrics.py` checks admin authorization, bounded telemetry behavior and aggregate definitions.

Run `.venv/Scripts/python.exe -X utf8 -m unittest tests.test_outcome_metrics -v`.

The aggregate test executes real SQL against a temporary in-memory SQLite table, supplying a UTC timezone function for the PostgreSQL-compatible expression. It verifies completed-search rate, distinct active accounts, return dates and exclusion of old rows. Other tests check the event/identity allowlist, best-effort failure, stale/unknown/unavailable operational states and rejection of non-admin access.

The linking regression creates historical web events before a Telegram link,
then Telegram events on another day. The real aggregate SQL must count one
returning actor and one subscription activation for those records, while keeping
an unrelated unlinked web account distinct.

Dependencies are unittest, FastAPI and SQLAlchemy. Side effects are restricted to memory and mocks. SQLite is not a verification of PostgreSQL migration, constraint or concurrency behavior; preserve that distinction in reports and add PostgreSQL integration checks when changing database-specific behavior.

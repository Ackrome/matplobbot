# Product events migration

`f7d8e9f0a1b2_add_product_events.py` follows `f6c7d8e9f0a1` and creates the `product_events` table.

## Interface and usage

Run the normal `alembic upgrade head` migration before starting code that records outcomes. `upgrade()` creates bounded event-name and deduplication-key fields, an aware timestamp, actor foreign keys and lookup indexes. `downgrade()` drops only this telemetry table and loses its event history.

## Dependencies and effects

Uses Alembic and SQLAlchemy. Requires existing `users` and `web_accounts`. The check constraint requires exactly one actor; both foreign keys cascade on account deletion. Deduplication keys are unique and nullable.

## Maintenance

Keep the migration consistent with `ProductEvent` in `shared_lib/models.py`. Validate one Alembic head, offline upgrade SQL and account erasure semantics. Do not rewrite earlier revisions to change production schema.

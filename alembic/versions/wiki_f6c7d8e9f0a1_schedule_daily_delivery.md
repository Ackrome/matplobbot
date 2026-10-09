# Daily delivery outbox migration

`f6c7d8e9f0a1_schedule_daily_delivery.py` follows `f5b6c7d8e9f0`.
`upgrade()` adds `delivery_kind` (default `change`) and nullable `expires_at` to
`schedule_change_deliveries`; `downgrade()` drops those fields.

Usage: apply `python -m alembic upgrade head` before starting the new scheduler.
The legacy table name and event/user unique constraint remain for compatibility.
Existing change notifications retain unlimited expiry; daily rows carry their
bounded catch-up deadline. No messages are sent by this migration.

Dependencies: Alembic and SQLAlchemy/PostgreSQL. Side effects: additive table
DDL only. Downgrading discards expiry metadata, so stop the new scheduler before
downgrade. Do not deploy application code requiring these fields before schema
migration. Keep the model and migration column defaults aligned.

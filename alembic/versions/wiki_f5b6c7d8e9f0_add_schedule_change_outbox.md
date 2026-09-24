# `f5b6c7d8e9f0_add_schedule_change_outbox.py`

## Purpose

Adds the PostgreSQL outbox used to retry Telegram notifications when a detected schedule change
cannot be delivered immediately.

## Public functions

- `upgrade()` creates `schedule_change_deliveries`, its delivery-ready index, the foreign key to
  `users`, and the unique `(event_key, user_id)` constraint.
- `downgrade()` removes the index and table.

## Usage

Apply with `python -m alembic upgrade head` before starting the updated scheduler. Downgrade one
revision only when pending or sent delivery history may be discarded safely.

## Dependencies and side effects

The migration depends on revision `f4a5b6c7d8e9`. Deleting a user cascades to their outbox rows.
Applying the migration does not create delivery rows or send Telegram messages.

## Maintenance notes

Keep the unique constraint aligned with `shared_lib.schedule_outbox`: one schedule-change event
may produce at most one Telegram delivery per application user. Schema changes must be mirrored
in `shared_lib.models.ScheduleChangeDelivery`.

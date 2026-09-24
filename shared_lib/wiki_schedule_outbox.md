# `schedule_outbox.py`

## Purpose

Provides the durable PostgreSQL outbox used by the scheduler for Telegram notifications about
schedule changes. Source schedule state and delivery state remain separate, so a Telegram outage
does not make a detected change disappear.

## Public API

- `build_schedule_change_event_key(...)` creates the stable transition identifier used for
  idempotent enqueue after a scheduler crash.
- `enqueue_schedule_change_deliveries(...)` inserts at most one row per event and application
  user.
- `commit_schedule_change_transition(...)` writes recipient rows, the new cached schedule, and
  matching subscription hashes in one database transaction. This is the scheduler's normal
  transition path.
- `claim_schedule_change_deliveries(...)` atomically claims ready work with `FOR UPDATE SKIP
  LOCKED` and reclaims abandoned processing rows after the lock timeout.
- `mark_schedule_change_delivery_sent(...)` finalizes a successful delivery.
- `reschedule_schedule_change_delivery(...)` returns a failed attempt to the queue with backoff,
  or marks it terminally failed.

## Usage example

```python
event_key = build_schedule_change_event_key("group", "42", old_hash, new_hash, checked_at)
await commit_schedule_change_transition(
    event_key=event_key,
    entity_type="group",
    entity_id="42",
    entity_name="PM23-1",
    schedule_data=new_schedule,
    new_hash=new_hash,
    deliveries=[{"user_id": 1, "chat_id": 1, "payload": "Schedule changed"}],
)
```

The scheduler claims and sends these rows through `deliver_pending_schedule_change_notifications`.

## Dependencies and side effects

The module uses `shared_lib.database.get_session`, the schedule/outbox ORM models, PostgreSQL
`ON CONFLICT`, and row locking. Calls commit their own short transactions. It never calls Telegram
directly.

## Maintenance notes

Keep the event-key inputs stable until `commit_schedule_change_transition` commits. The previous
cache timestamp distinguishes later repeated A→B transitions while preserving idempotency when the
same transition is retried. Telegram has no idempotency key, so a process crash after Telegram
accepts a message but before `mark_schedule_change_delivery_sent` can still produce one duplicate on
retry.

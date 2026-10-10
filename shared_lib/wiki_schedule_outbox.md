# `schedule_outbox.py`

Daily delivery also uses this outbox. `enqueue_daily_schedule_delivery` stores
the formatted message before sending, with a deterministic entity/date event key
and an expiry. `get_existing_schedule_deliveries` prevents repeated source fetches
for already prepared days. `get_schedule_outbox_health` returns status counts and
the oldest outstanding age without exposing messages or recipients.

Expired pending rows and abandoned processing rows with an exhausted final
attempt are explicitly marked failed. Completion/reschedule supports an expected
attempt count, preventing an old worker from overwriting a newer claim. Telegram
has no idempotency key: a successful send followed by an ambiguous acknowledgement
can still duplicate a message on retry; this is not an exactly-once guarantee.
The delivery worker claims one recipient immediately before sending instead of
reserving a large batch whose leases can expire while waiting. A pass stops
claiming after 45 seconds or 100 recipients; an individual send is bounded to
840 seconds, shorter than the 900-second recovery lease.

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
  matching subscription hashes together with the independent notification snapshot in one
  database transaction. `expected_revision` fences concurrent scanners; a conflict raises
  `ScheduleBaselineConflict` and leaves every write uncommitted. A missing baseline is initialized
  with no recipients. Interactive and periodic cache refreshes never modify this baseline.
- `get_schedule_notification_snapshot(...)`, `normalize_schedule_snapshot(...)` and
  `schedule_snapshot_hash(...)` load the notification baseline and exclude derived formatter fields.
- `cancel_inactive_schedule_deliveries(session, ...)` participates in pause/delete transactions;
  another active Telegram profile at the exact same entity/chat/topic keeps the event eligible.
  `is_schedule_delivery_current(...)` rechecks eligibility just before sending. An already in-flight
  Telegram send cannot be recalled, and pending private payloads are never redirected into a group.
- `claim_schedule_change_deliveries(...)` atomically claims ready work with `FOR UPDATE SKIP
  LOCKED` and reclaims abandoned processing rows after the lock timeout.
- `mark_schedule_change_delivery_sent(...)` finalizes a successful delivery.
- `reschedule_schedule_change_delivery(...)` returns a failed attempt to the queue with backoff,
  or marks it terminally failed.
- `prune_schedule_delivery_history(...)` deletes only terminal rows older than the configured
  retention (30 days by default, minimum 2), in bounded batches. The independent baseline remains.
  The two-day minimum exceeds every valid daily catch-up window and preserves daily event dedupe.

## Usage example

```python
event_key = build_schedule_change_event_key(
    "group", "42", old_hash, new_hash, checked_at, source_revision=baseline["revision"]
)
await commit_schedule_change_transition(
    event_key=event_key,
    entity_type="group",
    entity_id="42",
    entity_name="PM23-1",
    schedule_data=new_schedule,
    new_hash=new_hash,
    deliveries=[{"user_id": 1, "chat_id": 1, "payload": "Schedule changed"}],
    expected_revision=baseline["revision"],
)
```

The scheduler claims and sends these rows through `deliver_pending_schedule_change_notifications`.

## Dependencies and side effects

The module uses `shared_lib.database.get_session`, the schedule/outbox ORM models, PostgreSQL
`ON CONFLICT`, and row locking. Calls commit their own short transactions. It never calls Telegram
directly.

## Maintenance notes

Keep the event-key inputs stable until `commit_schedule_change_transition` commits. Pass the previous
baseline revision into `build_schedule_change_event_key(source_revision=...)`; it distinguishes
repeated A→B cycles even if timestamps happen to match. Capture that baseline before awaiting
the upstream source, so a delayed reply cannot reverse a newer concurrent scan. Telegram has no idempotency key, so a process crash after Telegram
accepts a message but before `mark_schedule_change_delivery_sent` can still produce one duplicate on
retry.

Claim cleanup reports newly expired/exhausted rows through its optional `summary` accumulator even
when it returns no claims. New terminal failures set `failed_at`; scheduler health and admin insights
expose the preceding hour's `recently_failed` count. Empty successful ticks do not erase that signal,
while historical failures age out of health automatically. Cancellation is a separate, nonfailure
outcome and clears the queued payload. Deploy migration `fe4e5f607182` with the old scheduler stopped
before backfill; start the new scheduler after the migration. Existing historical failures keep a
null `failed_at`, and already overwritten historical source payloads cannot be reconstructed.

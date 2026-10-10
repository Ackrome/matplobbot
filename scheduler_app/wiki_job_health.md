# Scheduler work heartbeats

`job_health.py` exports `monitor_job(operation, job)`, an async wrapper used by
the scheduler registrations. It records duration and success through the shared
content-free operational metrics helper. Exceptions remain exceptions; returned
`failed` or `rescheduled` counts make partial work unsuccessful.

Example: `scheduler.add_job(monitor_job("daily_schedules", send_daily_schedules),
trigger="cron", minute="*", kwargs=...)`.

Dependencies: Python functools/time and `shared_lib.operational_metrics`.
Side effects: bounded best-effort Redis heartbeat writes; no message content,
account IDs or raw exception strings. Keep the allowlisted operation names and
thresholds synchronized with actual schedules. Jobs that catch exceptions must
return failure counts; simply reaching the end does not prove successful work.
`tests/test_schedule_delivery.py` verifies partial and unexpected failure paths.

The monitored `schedule_updates` interval runs immediately when the scheduler
starts, then every two hours. A stable job ID, one maximum instance and coalescing
retain one scheduled poll; delivery still uses the durable baseline/outbox dedup.
The coalesced poll has no misfire expiry, so health-server setup taking longer
than APScheduler's default one-second grace cannot discard the startup run.
This avoids adding a fresh two-hour wait to a heartbeat that survived a restart,
which could otherwise exceed its existing three-hour freshness threshold.
`tests/test_scheduler_service.py` exercises actual APScheduler startup dispatch
and the next interval with synthetic work and no network or database connections.

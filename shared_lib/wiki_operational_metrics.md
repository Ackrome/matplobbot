# Operational outcomes

`operational_metrics.py` stores bounded Redis heartbeats for useful background work. Process health and job success remain separate signals.

## Public API and usage

Use `await record_operation("outbox_delivery", successful=True, duration_seconds=0.4)` for async jobs. Celery uses `record_operation_sync` to avoid sharing an event loop or database connection across worker forks. `await get_operational_snapshot()` returns last attempt/success/failure, duration, counters and stale/unknown/error/success states.

## Dependencies and effects

Uses the configured shared Redis URL. Keys under `mpb:operations:` expire after seven days; names are restricted to `OPERATIONS`. Writes increment success/failure counters and refresh the heartbeat. No message contents or identities are accepted. Use symbolic error codes, never exception text or credentials. Redis errors produce an unavailable report, not an empty healthy one. Recording is best effort and bounded.

## Maintenance

Keep stale thresholds consistent with actual scheduler intervals. On-demand compilation has no periodic stale threshold. Last success is not proof of every notification arriving. Admin insights and scheduler health consume the snapshot; regression tests distinguish absent data, storage failure and overdue work.

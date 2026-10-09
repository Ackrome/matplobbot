# Admin outcome insights

`insights_router.py` exposes operational and product summaries to administrators.

## API and usage

Authenticated administrators can request `GET /api/insights/operations` for job heartbeats, outbox counts/oldest pending age and the most recent schedule cache write. `GET /api/insights/product?days=30` returns aggregate outcomes over 1–90 days. Both use `Cache-Control: no-store`; anonymous and ordinary users cannot read them.

## Dependencies and effects

Uses `require_admin`, the shared database dependency, `ScheduleChangeDelivery`, `CachedSchedule` and the two metrics services. Endpoints are read-only and return no raw user event stream. The cache timestamp is global and does not mean every schedule is fresh. Redis failure is explicitly represented by `available=false`.

## Maintenance

Preserve authorization on the router when adding endpoints. Keep metric definitions aligned with `shared_lib/product_metrics.py` and the Stats UI. Queries must aggregate in the database rather than loading the event history into API memory. Validate date-window bounds and empty histories.

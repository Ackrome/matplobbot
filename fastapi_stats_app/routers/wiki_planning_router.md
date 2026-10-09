# Schedule planning API

`planning_router.py` defines `PlanningEntity`, `PlanningRequest` and
`POST /api/schedule/plan`. It is a bounded public read endpoint, matching ordinary
schedule discovery. It uses the existing schedule-data rate settings and shared
HTTP client; it never reads the caller's private subscription list.

Example body:

```json
{"entities":[{"entity_type":"group","entity_id":"123"}],"start_date":"2026-10-09","end_date":"2026-10-15","timezone":"Europe/Moscow","day_start":"08:00","day_end":"22:00","min_free_minutes":30}
```

Responses include conflicts, common free windows, source freshness/timestamps,
warnings and `incomplete`. Inputs are constrained to six entities, fourteen
days, supported calendar timezones, ordered daily times and 5–720 minute gaps.
Invalid requests return 422. Dependencies are FastAPI/Pydantic, rate limiting
and the shared planning/freshness services. Side effects are coalesced source
refresh and rate-counter writes. Maintain bounded inputs and do not expose
private calendar secrets; extend `tests/test_schedule_planning.py` with contract
changes. Register the router under `/api` in the application.

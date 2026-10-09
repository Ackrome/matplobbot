# Schedule conflicts and common free windows

`schedule_planning.py` exposes `validate_window`, pure `analyze_schedules`, and
async `load_schedule_plan`. The loader coalesces duplicate entities through the
shared schedule freshness service, unions their profile selections, applies
module/type filters, and includes source timestamps. The analyzer deduplicates
the same lesson returned by group, teacher and room sources, compares actual
overlapping intervals, and subtracts their union from each requested day.

Example: `await load_schedule_plan(client, [{"entity_type": "group", "entity_id":
"123"}], start_date=date(2026, 10, 9), end_date=date(2026, 10, 15))` compares one
week with 08:00–22:00 daily bounds and a 30-minute minimum free interval.

RUZ times are Moscow wall times; results use explicit offsets in the selected
calendar timezone. Limits: six unique entities, fourteen days, current cached
semester, 200 displayed conflicts. Missing/unverified sources or invalid lesson
times set `incomplete` and suppress free windows. Empty verified schedules are
authoritative. A room timetable gap never confirms physical availability.

Dependencies: shared freshness policy/service, canonical lesson-type/module
helpers, discipline mapping DB lookup. Side effects: cache/source reads and
coalesced refreshes, never schedule writes or notifications. Missing/null module
selection includes all modules; an explicit empty selection includes only common
lessons. Keep API and bot semantics aligned; test midnight offsets, duplicate
shared lessons, touching intervals, stale data and empty days when changing logic.

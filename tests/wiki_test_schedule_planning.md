# Planning regression tests

`test_schedule_planning.py` covers actual interval overlap, cross-source lesson
dedupe, different dates, midnight timezone shifts, free-window bounds, malformed
or stale sources, room caveats, profile union filtering, semester coverage,
API input bounds/rate limiting, and private Telegram ownership/HTML escaping.

Run: `.venv/Scripts/python.exe -m unittest tests.test_schedule_planning`.
The helpers `lesson` and `source` build deterministic in-memory schedule samples.
Test classes exercise the pure analyzer, async loader, FastAPI endpoint and bot
handler independently. Dependencies: unittest, FastAPI TestClient and application
modules. Network, DB, Redis and Telegram writes are mocked; no live data is used.
Maintain tests for empty verified schedules separately from missing/unverified
ones: only the former establish a free window. New interval formats or calendar
timezone options need conversion and boundary tests here.

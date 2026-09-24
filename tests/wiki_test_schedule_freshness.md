# `test_schedule_freshness.py`

## Purpose

Regression tests for website schedule stale-while-revalidate behavior and per-entity request coalescing.

## Coverage

- A fresh shared cache skips RUZ entirely.
- A stale cache is replaced by a successful live response.
- Twenty concurrent viewers produce one upstream call.
- RUZ failure serves stale data when available and fails clearly when no cache exists.
- A successful empty RUZ list authoritatively removes old lessons.

## Usage

```powershell
.venv\Scripts\python.exe -m unittest tests.test_schedule_freshness
```

## Dependencies and side effects

All database, Redis lease, and RUZ calls are mocked. Tests may create short-lived asyncio tasks but clean the shared task registry before and after each case.

## Maintenance notes

Keep the concurrency assertion at more than one viewer. When adding freshness states, extend both state assertions and the frontend/API contract tests rather than weakening the single-flight guarantee.

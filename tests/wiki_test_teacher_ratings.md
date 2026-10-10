# Teacher ratings backend tests

`test_teacher_ratings.py` covers the service, public router and cache migration.
Run with the project Python:

```sh
python -m unittest tests.test_teacher_ratings -v
```

`TeacherCacheTests` executes actual SQLAlchemy statements against SQLite through
`AsyncSessionBridge`; database results are not mocked. It covers durable cache
reuse across service instances, negative/failure TTLs, null statistics, stale
fallback, concurrent local lookup coalescing, database leases and stale-writer
rejection, timeout recovery, request versus shutdown cancellation, and bounded
refresh capacity. Pagination fixtures cover complete unique matches, ambiguity,
missing pages, repeated cards and changing totals before publishing an identity.

`HtmlResponse` / `HtmlSession` replace only the external transport. Public HTML
fixtures from `test_teacher_rating_source` exercise the real parser-to-cache
path. `HttpBoundaryTests` checks forbidden redirects, HTML size/MIME/compression,
retry/request budgets, concurrent requests and request-start spacing.
`TeacherRatingApiTests` uses FastAPI TestClient for the public response/UTC/null
contract, query bounds and limiter-before-lookup behavior.
`TeacherRatingMigrationTests` runs actual Alembic operations, uniqueness/status
constraints and downgrade while preserving an unrelated table.

Dependencies: unittest, SQLAlchemy, Alembic, FastAPI TestClient and the source
parser fixtures. Tests make no external source requests, touch no production DB,
and send no messages. Keep each fixture's observed source structure intact and
change expected behavior only after checking real source/identity semantics.

# v1 release readiness evidence — 2026-10-10

These reports distinguish development checks from accepted immutable release evidence.
The local RC uses working-tree images and cannot be used as a deployment manifest.

| Check | Result | Evidence |
| --- | --- | --- |
| Application regression suite | 650 tests, 8 platform/optional skips; passed | Root project `.venv`, `coverage run --branch -m unittest discover -s tests -v` |
| Application-only coverage | 52.62%, including unimported modules | `bot`, `fastapi_stats_app`, `scheduler_app`, `shared_lib`; floor 50% |
| CI critical Ruff / mypy | Passed / all 6 configured files passed | Same commands as CI |
| Locked dependency audit | 46 packages, no known vulnerabilities reported | CI `pip_audit --strict`, existing narrow joblib exception retained |
| Real local service RC | Passed | [rc-acceptance-local.json](rc-acceptance-local.json) |
| Production snapshot restore | 21 tables matched; 5.49 seconds | [production-restore.json](production-restore.json) |
| Migration of restored production data | Passed; all original rows preserved | [production-migration.json](production-migration.json) |
| Isolated real rollback | Source, private configuration, all 9 runtime image IDs, old admin login and schema verified | [rollback-local.json](rollback-local.json) |
| Read-only live preflight | No pending/processing rows; 19 historical terminal failures | [production-preflight.json](production-preflight.json) |
| Offline delivery grouping/load | 1,000 recipients, no duplicate sends | [normal](delivery-load-normal.json), [degraded](delivery-load-degraded.json) |
| Account UI | Desktop/mobile RU; mobile EN/dark; actual logout-all confirmed | [screenshots](screenshots/) |

The local RC uses real PostgreSQL, Redis, HTTP API, Celery, renderer executables and
scheduler delivery code. Only external Telegram and RUZ boundaries use synthetic
fixtures. It covers HTTP throttling, active/new WebSocket revocation, account
isolation/export/delete, calendar feeds, restart persistence, failed delivery retry,
PostgreSQL concurrent claiming/CAS/cancellation, and isolated backup restoration.

The production restore and migration used a fresh private snapshot transferred off
app-vm. No bot, API or scheduler was started with those real data; PostgreSQL had no
external network. Dumps, row-witness metadata and environment secrets remain outside
this repository. The migration report contains aggregate verification only.

The synthetic load runs continuously drain batches: their elapsed times are not
production latency or maximum supported audience. They exclude the minute scheduler
cadence, upstream rate limits and production host contention. The live preflight's
2.8 GiB free disk is a rollout headroom concern, not evidence of a current outage.

Final release acceptance belongs to the CI-generated manifest for the exact commit
and four image digests. Deployment freezes the existing observed support-container
image IDs, verifies the production schema and performs positive authenticated smoke
checks before advancing the last-successful pointer. See [the release runbook](../../release-runbook.md).

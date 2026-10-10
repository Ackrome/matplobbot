# v1 release readiness evidence — 2026-10-10

These reports distinguish development checks from accepted immutable release evidence.
The local RC uses working-tree images and cannot be used as a deployment manifest.

The self-hosted CI runner's inactive September 4 Buildx cache was removed after
fresh checks found no container, process mount or open-file references. Free space
increased by 11,774,816,256 bytes to 12,786,122,752 bytes; all nine images and the
running builder were preserved. This was CI cache maintenance, not release
acceptance: [runner-cache-reclaim.json](runner-cache-reclaim.json).

The agreed ten release-readiness items are implemented as follows:

1. Rendering uses a mandatory non-root Linux namespace sandbox with bounded
   processes, output and runtime. LaTeX ignores local configuration files.
2. Studio assets require authenticated requests. Verified raster images can be
   previewed; other legacy assets download with restrictive response headers.
   Asset URLs no longer carry session tokens.
3. Notification comparison uses its own durable database snapshot and revision
   checks, so an interactive timetable refresh cannot consume a change.
4. Paused/deleted subscriptions cancel unsent deliveries; claimed deliveries
   recheck eligibility. Recent terminal failures and bounded retention are visible.
5. Login budgets are shared through Redis. Session revocation survives restarts,
   supports current/all sessions and reaches existing WebSocket connections.
6. Web-to-Telegram destinations survive onboarding and intermediate menus, then
   resume once for the correct user, bot and chat.
7. Deployment binds source, four image digests, assets/configuration and schema;
   preserves support image IDs and prior private state; finalizes after smoke.
8. A real production snapshot was restored and its original rows checked through
   the new migrations. Matching private configuration was retained off-host.
9. CI requires built-image acceptance with real database, queue, API, worker,
   renderer and restore checks. Coverage excludes test code and includes unimported
   application modules.
10. Live queues were inspected, failure/retention behavior was tested, and grouped
    delivery was exercised for 1,000 synthetic recipients. The limitations below
    distinguish that evidence from production capacity.

| Check | Result | Evidence |
| --- | --- | --- |
| Application regression suite | 671 tests, 9 platform/optional skips; passed | Root project `.venv`, `coverage run --branch -m unittest discover -s tests -v` |
| Application-only coverage | 52.62%, including unimported modules | `bot`, `fastapi_stats_app`, `scheduler_app`, `shared_lib`; floor 50% |
| CI critical Ruff / mypy | Passed / all 6 configured files passed | Same commands as CI |
| Locked dependency audit | 46 packages, no known vulnerabilities reported | CI `pip_audit --strict`, existing narrow joblib exception retained |
| Real local service RC | Passed | [rc-acceptance-local.json](rc-acceptance-local.json) |
| Ubuntu runner service RC diagnostic | Passed, including 23-table restore and cleanup | [rc-ubuntu-diagnostic-40b.json](rc-ubuntu-diagnostic-40b.json) |
| Ubuntu runner sandbox compatibility | 11 distinct tests passed, including all six render formats and outer/inner kernel-access restrictions | [worker-host-sandbox.json](worker-host-sandbox.json); published `40b1606` worker with updated host policy, not final release acceptance |
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

The Ubuntu diagnostic reused published `40b1606` application images with the updated
orchestration, explicit worker AppArmor policy and TCP database readiness checks.
Its report is marked `working-tree`: it verifies the runner's actual service and
kernel compatibility, but cannot attest a different source commit or replace the
mandatory final-image CI acceptance.

The first legacy rollback has a concrete compatibility restriction. Do not use
`--compatible-schema fe4e5f607182` to return to the observed `9fac7e87` runtime:
its API accepts newly revoked JWTs with the unchanged signing key, and its writer
does not advance notification snapshots, causing duplicate logical transitions
after a later forward rollout. Both effects were reproduced with exact legacy
source and synthetic relational data in [legacy-compatibility.json](legacy-compatibility.json).
The default schema refusal must remain in force; the same-schema rollback drill
does not certify this path. Recovery requires the separate maintenance/restore
and session-invalidation decision described in the release runbook.

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

# v1 release readiness evidence — 2026-10-10

These reports distinguish development checks from accepted immutable release evidence.
The local RC uses working-tree images and cannot be used as a deployment manifest.

The final application release is `1302e8b2287b008d9c0cbe1f1fae87ef9780c24f`.
[GitHub Actions attempt 2](https://github.com/Ackrome/matplobbot/actions/runs/38048719980)
passed, and [Jenkins 348](http://jenkins-vm.panthera-banjo.ts.net:8080/job/matplobbot-deploy/348/)
automatically ran all six production smoke checks and finalized that exact commit.
Independent verification passed all 27 release-state/runtime checks; both signing
and mail-encryption keys remained present and unchanged. Production had 9.15 GiB
free after deployment. Later documentation-only commits do not change this accepted
application identity.

Existing website users need to sign in again once: tokens issued before the new
durable session-revocation contract lack its required claims. Accounts, projects
and subscriptions remain stored.

The self-hosted CI runner's inactive September 4 Buildx cache was removed after
fresh checks found no container, process mount or open-file references. Free space
increased by 11,774,816,256 bytes to 12,786,122,752 bytes; all nine images and the
running builder were preserved. This was CI cache maintenance, not release
acceptance: [runner-cache-reclaim.json](runner-cache-reclaim.json).

The later `1302e8b` worker build exhausted the runner's filesystem before RC or
deployment; the runner could not write its diagnostic log. The existing 80 GiB
virtual disk had a 39 GiB root LV and about 39 GiB unallocated inside its volume
group. After a metadata backup and exact-size checks, the mounted ext4 filesystem
and LV were grown by 20 GiB to 59 GiB, retaining 19 GiB of VG reserve. Available
space became 28.16 GiB; all images, builder containers and volumes were preserved.
See the [failed attempt](runner-disk-failure-1302.json),
[capacity change](runner-capacity.json) and
[independent verification](runner-capacity-verification.json). LVM metadata is
not a filesystem-data backup. The failed jobs were retried for the same source.

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
| Application regression suite | 679 tests, 9 platform/optional skips; passed | Root project `.venv`, `coverage run --branch -m unittest discover -s tests -v` |
| Application-only coverage | 52.62%, including unimported modules | `bot`, `fastapi_stats_app`, `scheduler_app`, `shared_lib`; floor 50% |
| Final-source GitHub validation | 679 tests, 9 skips; 52.45% coverage; types and dependency audit passed | [CI run 38048719980](https://github.com/Ackrome/matplobbot/actions/runs/38048719980), source `1302e8b2287b008d9c0cbe1f1fae87ef9780c24f`; successful validation from attempt 1 is retained in attempt 2 |
| Actual Jenkins-user quality replay | 677 tests, 9 skips; 52.52% coverage; pinned Node 24.21.0 verified | [jenkins-node-gate.json](jenkins-node-gate.json); isolated source diagnostic, not a deployment |
| CI critical Ruff / mypy | Passed / all 6 configured files passed | Same commands as CI |
| Locked dependency audit | 46 packages, no known vulnerabilities reported | CI `pip_audit --strict`, existing narrow joblib exception retained |
| Immutable final-image RC | All 12 check groups passed; all 23 tables restored in 15.92 seconds | [Accepted manifest](release-manifest-accepted.json), [RC report](rc-acceptance-ci.json); exact source `1302e8b2287b008d9c0cbe1f1fae87ef9780c24f` |
| Automatic production acceptance | Jenkins 348: six smoke checks, exact completion marker, successful finalization; 27 independent checks passed | [Production release report](production-release-1302.json) |
| Production key continuity | New accepted API container; signing and mail-encryption keys present and unchanged | [Security report](production-release-security-1302.json); private values and fingerprints stay on the server |
| Retained managed rollback target | Successful `8662`, same schema, saved source/configuration/policies and all nine images available | [Production release report](production-release-1302.json); no live rollback was performed |
| Real local service RC | Passed | [rc-acceptance-local.json](rc-acceptance-local.json) |
| Ubuntu runner service RC diagnostic | Passed, including 23-table restore and cleanup | [rc-ubuntu-diagnostic-40b.json](rc-ubuntu-diagnostic-40b.json) |
| Ubuntu runner sandbox compatibility | 11 distinct tests passed, including all six render formats and outer/inner kernel-access restrictions | [worker-host-sandbox.json](worker-host-sandbox.json); published `40b1606` worker with updated host policy, not final release acceptance |
| Production snapshot restore | 21 tables matched; 5.49 seconds | [production-restore.json](production-restore.json) |
| Migration of restored production data | Passed; all original rows preserved | [production-migration.json](production-migration.json) |
| Isolated real rollback | Source, private configuration, all 9 runtime image IDs, old admin login and schema verified | [rollback-local.json](rollback-local.json) |
| Read-only live preflight | No pending/processing rows; 19 historical terminal failures | [production-preflight.json](production-preflight.json) |
| Production worker cache maintenance | 13 obsolete images removed; 9,569,153,024 bytes reclaimed; 10.40 GiB available afterward | [Exact targets and preservation checks](production-worker-cache-reclaim.json) |
| Offline delivery grouping/load | 1,000 recipients, no duplicate sends | [normal](delivery-load-normal.json), [degraded](delivery-load-degraded.json) |
| Account UI | Desktop/mobile RU; mobile EN/dark; actual logout-all confirmed | [screenshots](screenshots/) |
| Public production UI at bootstrap | Schedule, lesson details, discipline assessment and complete cached semester rendered without observed JavaScript errors | [Browser report](browser-production-8662.json); accepted `8662` before the later Jenkins-only correction |
| Public UI after final deployment | Reloaded schedule rendered; no captured JavaScript warnings or errors | [Browser report](browser-production-1302.json) |

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

Jenkins 347 exposed a false green in its streamed smoke shell: the first Docker
exec command consumed the remaining script from stdin. The application was
running, but the successful-release pointer correctly remained unchanged. The
exact smoke body was executed from a saved file with closed stdin; all six smoke
checks and finalization passed. This manual recovery is recorded explicitly in
[production-bootstrap-8662.json](production-bootstrap-8662.json); key continuity
is recorded as booleans in [production-bootstrap-keys.json](production-bootstrap-keys.json).
The durable fix uses a tracked script, verifies successful state for the expected
SHA, and makes Jenkins require its explicit completion marker. The old failure
and repaired path are covered by [smoke-stdin-regression.json](smoke-stdin-regression.json).

The synthetic load runs continuously drain batches: their elapsed times are not
production latency or maximum supported audience. They exclude the minute scheduler
cadence, upstream rate limits and production host contention. The initial live
preflight had only 2.8 GiB free disk. After the first accepted rollout, thirteen
unreferenced worker image cache entries were removed using exact IDs with verified
immutable registry recovery references. All sixty other images, ten containers
and all volumes were preserved. The last Docker client timed out during garbage
collection; no deletion was retried, and subsequent read-only checks verified all
thirteen targets and their exclusive snapshots were gone. Actual free space grew
by 8.91 GiB to 10.40 GiB; see the cache report for the measured byte counts.

Final release acceptance belongs to the CI-generated manifest for the exact commit
and four image digests. Deployment freezes the existing observed support-container
image IDs, verifies the production schema and performs positive authenticated smoke
checks before advancing the last-successful pointer. See [the release runbook](../../release-runbook.md).

On 2026-11-04, the runner reached 100% root usage after a failed build for revision `67e7b83`. A fresh idle check found four unreferenced images from that failed build and no active Runner.Worker process. Those exact image IDs were removed serially without force. Free space increased from 0 to 12,230,352,896 bytes, all three builder containers and the current builder remained intact, and the runner, Docker and containerd services stayed active. Historical image sets were retained because GHCR manifest verification returned 403 on the runner. This is runner maintenance evidence and does not attest RC acceptance. See [runner-disk-cleanup-2026-11-04.json](runner-disk-cleanup-2026-11-04.json).

Run 465 (attempt 2) rebuilt all four services, then failed in the RC acceptance step before producing `rc-acceptance.json`. The manifest was created and Docker pulled Bot, API and Scheduler. The Worker digest from that manifest was still absent on the runner, which had only 5.84 GB free at that point. The failed job left a Buildx builder with a 3.269 GB state volume. After confirming the runner was idle, that exact orphan builder was removed and Docker removed its linked volume. The runner now has 9,290,530,816 bytes free with the three retained builders and services healthy. The missing Worker pull and the absent RC report indicate a likely headroom failure before the acceptance tests, but the job log does not retain the direct error line. See the follow-up fields in [runner-disk-cleanup-2026-11-04.json](runner-disk-cleanup-2026-11-04.json).

After that failed attempt, the runner root LV was expanded online by 15 GiB from 63,346,573,312 to 79,452,700,672 bytes. The ext4 filesystem was completed at 77,883,056,128 bytes, with 24,499,732,480 bytes available on the final runner check. Four GiB remain free in the volume group. No VM reboot or Proxmox virtual-disk change occurred. Container and image IDs, the protected Buildx builder and all three services were verified unchanged. The first `lvextend --resizefs` wrapper detached after the LV growth, so `resize2fs` was run separately and verified before completion. The VG backup is retained on the guest at `/root/matplobbot-runner-maintenance-20261104/ubuntu-vg-before-15g-growth.conf` with mode 0600. See the `lvm_expansion` section in [runner-disk-cleanup-2026-11-04.json](runner-disk-cleanup-2026-11-04.json).

Run 465 attempt 3 was rerun after the capacity change. The four service builds, immutable release binding, real-service RC acceptance, release evidence upload, Soft Cleanup and Jenkins trigger all passed. The run completed successfully for source `67e7b83e8bff1083fbc80dc1d68c9f5796a60910`. The runner ended idle with 13,949,857,792 bytes free and its three protected builder containers and services active. See the `rerun_attempt` section in [runner-disk-cleanup-2026-11-04.json](runner-disk-cleanup-2026-11-04.json).

Jenkins build `353` failed on app-vm while pulling the Worker image because its 100G guest disk was full. The guest LV first used 30 GiB of its existing VG reserve and then another 15 GiB while the deployment was retried. Proxmox `local-hdd` had ample capacity, so VM 103's virtual disk was expanded online from 100G to 200G. The guest partition and PV were grown, the root LV was extended by 80 GiB, and ext4 now has 114,216,701,952 bytes free with 24 GiB retained in the VG. Jenkins build `354` then completed successfully with all six post-deploy smoke checks. Production containers and Docker services are healthy. See [app-vm-disk-expansion-2026-11-05.json](app-vm-disk-expansion-2026-11-05.json).

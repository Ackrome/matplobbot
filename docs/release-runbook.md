# Release and recovery contract

The application release identity is the full Git commit plus four OCI image digests,
the tracked deployment-file hashes and the single Alembic head. The Python shared
package version is an independent package identifier. A `latest` tag or a green
unit-test job alone is not an accepted application release.

## Acceptance and deployment

On a Docker host with AppArmor, review `security/worker-apparmor.template` and run
`sudo python3 scripts/worker_security.py install --root .` from the reviewed
candidate before RC or deployment. This adds a content-hash-named policy under
`/etc/apparmor.d`, verifies it is loaded, and preserves older policies. It changes
no global user-namespace setting. The ordinary deployment user can then run
`python3 scripts/worker_security.py check`; the positive compile remains required
because that user may not read securityfs. Daemons without AppArmor omit this
selection. Do not replace the named policy with `apparmor=unconfined` on Ubuntu 24:
that still invokes its restricted unprivileged-user-namespace profile.

Both base Compose files deliberately omit AppArmor selection. The RC/deploy helpers
add exactly one verified named option in their generated worker override. Direct
Compose operators must provision the same policy and supply a worker
`security_opt` override containing the option returned by `check`; retain the
base seccomp and no-new-privileges options. Use the release helper for accepted
deployments and keep older hash-named policies through the rollback window.

The worker/probe alone also use `systempaths=unconfined`, as documented by Moby
for nested rootless process sandboxes: Docker's masked parent `/proc` paths can
make Linux reject a new PID-namespace procfs mount. The renderer still mounts a
fresh `/proc` in its own PID namespace; it never binds the worker's process view.
Non-root UID, zero effective/permitted/bounding capabilities, no-new-privileges,
read-only root, seccomp and resource limits remain mandatory. The actual sandbox
suite checks both outer and inner processes cannot open sensitive kernel controls
for writing. Do not apply this exception to other services or add SYS_ADMIN.

GitHub Actions validates the source, builds all four images with its exact source
revision label, then runs `scripts/rc_acceptance.py` against those digests. This
mandatory step creates an internal Docker network, fresh PostgreSQL and Redis,
and the actual API, Celery worker and scheduler image. No host ports, production
environment file or real users are used. It checks migrations, signed synthetic
Telegram login, ownership, project persistence across API restart, real compiler
artifacts, worker isolation, calendar feeds, account export/delete, session
revocation, shared Redis Lua limits, scheduler delivery retry and PostgreSQL locks.
The external boundaries are a seeded RUZ cache and a local HTTP fixture returning
Telegram-shaped responses; this does not certify live Telegram/RUZ availability.

The same run exports a consistent PostgreSQL snapshot and restores it into a second
fresh `--network none` PostgreSQL container. It compares the schema and every public
table's row count/content fingerprint, including project binary data and session
revocations. Both disposable databases and their volumes are removed. Missing Docker,
denied worker namespaces, failed compilation or failed restore fail the job.

Only a passed report can be embedded in `release-manifest-accepted.json`. Jenkins
receives `SOURCE_COMMIT` and `RELEASE_MANIFEST_B64`, checks out that exact commit,
reruns quality checks and prepares a detached candidate worktree on the application
host. Tracked edits and unexpected untracked deployment inputs fail verification.
The candidate is validated and its images downloaded before maintenance starts.
The destination host then runs a disposable positive LaTeX compile from the accepted
worker digest under the production security profile, no network/environment/mounts
from production, and a 120-second bound. This proves the destination kernel permits
the sandbox; a denied namespace fails while the old site is still running.
`release_deploy.py prepare` saves the old private configuration and observed legacy
runtime if needed, retains recovery tools, writes an attempt marker, stops every
service with a host bind mount, then switches the live checkout. This bounded
maintenance window prevents new frontend/config files being served with the old
API. Jenkins writes the new credentials only after this baseline is safe.

For an existing Jenkins job, new pipeline parameters must be installed before the
first `buildWithParameters` call. The workflow invokes
`scripts/jenkins_release_parameters.py --apply` with its existing Jenkins identity
and verified LAN address. It adds missing string `SOURCE_COMMIT` and text
`RELEASE_MANIFEST_B64` definitions with empty defaults, binds the known Git SCM
branch to `${SOURCE_COMMIT}`, and disables lightweight checkout so parameter
expansion loads `Jenkinsfile.groovy` from the accepted commit itself. Unexpected
SCM/branch/script configurations fail. All other job settings are preserved. It
rereads parameters and SCM binding before queuing a build. A Read/Configure
permission failure stops the workflow with an operator instruction; it never runs
the old deployment pipeline to bootstrap parameters. The CLI is read-only unless
`--apply` is supplied. Avoid concurrent manual job configuration edits.

`bash deploy.sh --manifest .release-state/accepted.json` verifies source/digests,
backs up an existing running PostgreSQL database, stops the old scheduler before
the notification-baseline migration, migrates and starts the accepted services.
The dedicated admin bootstrap must succeed. Jenkins then runs positive authenticated
smoke checks and invokes `bash deploy.sh --finalize`. Only finalize advances
`.release-state/current.json`; failed startup/bootstrap/smoke leaves the previous
successful pointer intact. Previous source, configuration and runtime image IDs are
retained. Production deployment does not prune images.

The first deployment of durable session revocation rejects older JWTs that lack
the required token ID and account-version claims. Existing website users must
sign in again once; their accounts, projects and subscriptions remain stored.
Preserving the signing key does not exempt legacy tokens from the new checks.

Preparation requires five healthy existing support services: PostgreSQL, Redis,
Caddy, frontend nginx and proxy. Their observed runtime image IDs are frozen into
the deployment override. Deployment uses `--no-build --pull never`; no mutable
support image is resolved or proxy rebuilt during an application release. Support
bootstrap/repair or a deliberate support-image upgrade is a separate operation
with its own validation. The RC tests the four application images; it does not
claim fresh-build reproducibility of the observed support stack.

Keep `.release-state` private and backed up to an access-controlled location. Its
configuration snapshots contain signing and mail-encryption keys. The Docker data
volumes and external secret stores are not replaced by a Git checkout. Do not prune
retained images or delete backups during the rollback window. Operator-managed
proxy/TLS stores remain external dependencies and need their own backup policy.

## Restore drill

For a recently acquired production backup, run the backup helper on the source host
without starting or changing application services:

```bash
python3 scripts/release_backup.py backup --output /private/backup/production.dump
```

Transfer `production.dump` and `production.json` through an authorized private
channel. The JSON contains hashes/counts, not row values. On a host with Docker:

```bash
.venv/bin/python scripts/release_backup.py restore-drill /private/backup/production.dump \
  --output /private/backup/production-restore-report.json
```

On Windows use `.venv/Scripts/python.exe`. This command has no production target
option: it creates a random isolated PostgreSQL container, verifies the dump hash,
restores, compares witnesses, and removes only its own container/anonymous volume.
Record the report time, schema and dump hash alongside the private backup provenance.
A synthetic RC restore proves the mechanism; it does not prove that the latest
production backup is complete or that production secrets are recoverable. A real
production restore drill must be recorded separately. The tool verifies DB contents;
it does not start delivery services or send user notifications.

## Rollback

Review the recorded state and preserve the smoke helper below before invoking
rollback. After a failed deployment it targets the last successful release; after
a completed release it targets the preceding one. It restores that source, private configuration and saved
image IDs without pulling/building, running migrations or deleting data volumes.
It refuses a different database head. Only after an explicit old-code/schema
compatibility review may an operator supply `--compatible-schema <current-head>`.
For this first rollout, the observed `9fac7e87bc025508397664083a4df75302a61583`
runtime at `fc2c3d4e5f60` is **not compatible** with a rollback retaining
`fe4e5f607182`: do not use `--compatible-schema fe4e5f607182` for that legacy
target. Keep the default schema refusal. Isolated tests using its exact source
show that legacy auth accepts a JWT revoked by the new API when the signing key
is restored unchanged. Its notification writer also leaves the new baseline
stale, allowing a subsequent forward rollout to enqueue an already observed
change again. See [the synthetic reproduction](reports/v1-release/legacy-compatibility.json).
The successful same-schema local rollback drill does not certify this transition.
Use a separately reviewed recovery plan: restoring the pre-migration database
requires an explicit decision about intervening writes and website-session
invalidation, while preserving the matching mail-encryption keys. Do not resume
a forward rollout after legacy operation against the new schema without resolving
the notification baseline and testing that recovery path.
The collision-safe admin bootstrap resynchronizes the restored smoke credentials.
For a successful managed target, retain the reviewed current `release_smoke.sh`
**before** rollback changes the checkout. Accepted `8662f8120838c1269526ea7163299e1bd03fac0c`
predates that tracked shell file, but its `deploy.sh --finalize` and four Python
recovery helpers support this procedure. Review the target selected from
`current.json` when `attempt.json` exists, otherwise `previous.json`; never derive
the rollback target from `accepted.json`, which may still describe the newer candidate.
Run the following as `deploy` from the application checkout. Set `TARGET_SHA`
explicitly to the reviewed successful target; the commented `8662` value is an
example, not a command to select whichever release happens to be available.

```bash
set -euo pipefail
umask 077
# Example only, after reviewing the recorded rollback target:
# export TARGET_SHA=8662f8120838c1269526ea7163299e1bd03fac0c
: "${TARGET_SHA:?Set TARGET_SHA to the reviewed full accepted rollback commit}"
printf '%s' "$TARGET_SHA" | grep -Eq '^[0-9a-f]{40}$'

TARGET_SHA="$TARGET_SHA" python3 - <<'PY'
import json
import os
from pathlib import Path

state = Path(".release-state")
name = "current.json" if (state / "attempt.json").exists() else "previous.json"
target = json.loads((state / name).read_text(encoding="utf-8"))
if (
    target.get("legacy")
    or target.get("status") != "successful"
    or target.get("manifest", {}).get("commit") != os.environ["TARGET_SHA"]
):
    raise SystemExit("Recorded rollback target is not the expected accepted release")
PY

git diff --quiet HEAD -- scripts/release_smoke.sh
REVIEWED_SOURCE_SHA="$(git rev-parse --verify HEAD)"
printf '%s' "$REVIEWED_SOURCE_SHA" | grep -Eq '^[0-9a-f]{40}$'
install -d -m 700 .release-state/recovery-tools
SMOKE_COPY=".release-state/recovery-tools/release_smoke-${REVIEWED_SOURCE_SHA}.sh"
cp -- scripts/release_smoke.sh "$SMOKE_COPY"
chmod 600 "$SMOKE_COPY"
cmp -s scripts/release_smoke.sh "$SMOKE_COPY"
bash -n "$SMOKE_COPY"

python3 .release-state/recovery-tools/release_deploy.py rollback </dev/null
SMOKE_LOG="$(mktemp .release-state/rollback-smoke.XXXXXX.log)"
bash "$SMOKE_COPY" "$TARGET_SHA" </dev/null | tee "$SMOKE_LOG"
grep -Fxq "Release smoke and finalization completed: $TARGET_SHA" "$SMOKE_LOG"
```

The retained script runs positive health, administrator login, authenticated REST
and WebSocket, and anonymous-access checks. It then finalizes and verifies the
successful target pointer and absence of pending markers. Do not finalize again.
Keep `pipefail`, closed stdin and the exact completion-marker check. This recipe
does not accept `observed-legacy` records or override schema compatibility.

If a separately reviewed compatible legacy recovery has no manifest tools in its
restored checkout, the four retained Python helpers remain available. Run its
reviewed authenticated smoke procedure before finalizing with the retained helper:

```bash
python3 .release-state/recovery-tools/release_deploy.py rollback
# After authenticated smoke passes:
python3 .release-state/recovery-tools/release_deploy.py finalize
```

An incompatible schema requires a separately authorized maintenance restore of the
pre-migration backup and its matching encryption keys, with an explicit decision
about writes since that backup. The tool deliberately does not automate production
database replacement or Alembic downgrade. The first adoption of this release
format has no prior accepted manifest. Preparation records its actual source hashes,
schema, configuration and running image IDs as an explicitly `observed-legacy`
baseline, so early checkout/env-write failure can restore it. That observation is
not a retroactive RC pass. Schema incompatibility still requires the maintenance
restore/compatibility decision above.

## Local evidence and coverage

For development evidence, pass four `--local-image service=tag` arguments to
`scripts/rc_acceptance.py`. Such reports are marked `-working-tree` and cannot be
attested or deployed as an immutable release. Dockerfiles expose `PYTHON_BASE_IMAGE`
and `WORKER_BASE_IMAGE` build arguments so cached local bases can be used for this
check. CI still tests and records the final immutable image digests.

Coverage measures branches and statements in `bot`, `fastapi_stats_app`,
`scheduler_app` and `shared_lib`, including unimported application modules and
excluding test files. The pre-change application-only baseline was 50.30%; the
initial fail-under floor is 50%, replacing the misleading combined test/source
metric and 10% floor. PR trend comparison uses this same scope for both revisions.
Ordinary cross-platform unit runs may skip Linux compiler integration; the separate
mandatory built-image acceptance step explicitly enables it and allows no skip for
an unavailable sandbox.

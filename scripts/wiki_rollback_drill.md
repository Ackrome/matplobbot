# Isolated rollback drill

The temporary fixture copies `worker_security.py` with the three release helpers,
so it exercises recovery with the current helper dependency graph. The observed
legacy fixture intentionally retains its historical security selection; managed
profile rollback additionally requires the release policy/positive-probe tests.

`rollback_drill.py` runs the actual `release_deploy.py rollback` and `finalize`
commands against a temporary Git repository and unique Docker Compose project.
It never reads the real `.env`, release snapshots or database. All credentials,
account records and commits are synthetic. The network is internal and no host
ports are published. Existing application images are required; no registry pull
or production deployment occurs.

`fixture_compose()` and `fixture_environment()` build the isolated topology and
settings. `drill(root, api_image, bot_image)` migrates real PostgreSQL with the bot
image, runs the actual API and Redis, records an observed-legacy baseline, changes
tracked source/private settings/password and runtime image, then invokes rollback.
Real HTTP verifies the old password returns and the new password stops working.
It checks frontend canary content, schema/account preservation, image IDs and
pointer advancement only after smoke. Other application and ingress roles idle;
this is rollback mechanics evidence, not production load/ingress proof.

Usage from the repository root:

```powershell
$env:PYTHONUTF8='1'
.venv/Scripts/python.exe scripts/rollback_drill.py --output "$env:TEMP/rollback-local.json"
```

Dependencies: Docker Compose, local API/bot images, PostgreSQL 15/Redis 7 images,
Git and project Python. Side effects are temporary fixture files, unique local
containers/volume/network and a label-only candidate image. Cleanup runs on both
success and failure and verifies no resources with the project label remain.
Only the requested JSON report survives. Reports contain helper hashes and image
IDs but exclude credentials and JWTs. Keep the observed-legacy fixture explicit;
do not manufacture a GHCR release attestation from these development images.

The PostgreSQL fixture healthcheck uses TCP loopback, excluding the image's
temporary Unix-only initialization server before migration starts.

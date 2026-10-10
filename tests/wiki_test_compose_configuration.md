# `test_compose_configuration.py`

PostgreSQL healthchecks must use TCP loopback in both Compose files; this excludes
the temporary Unix-only initialization server and preserves configured user/DB
variable expansion.

Smoke tests now use the tracked `scripts/release_smoke.sh` body. The fake Docker
command actively consumes stdin; byte-mode input preserves LF on Windows and
reproduces the old streamed-shell exit-zero failure. Repaired smoke execution
must reach all checks and finalization without consuming input. Wrong accepted
commit/pending-state cases fail. An executable Jenkins wrapper test also rejects
SSH success with absent/wrong completion text, so no source-only assertion can
substitute for the acceptance protocol.

## Purpose

Protects the intentional relationship between the local and production Docker Compose stacks without introducing a separate `compose.dev` file.

## Coverage

- Both stacks expose the same shared services; the credentials-backed egress proxy is the only production-only service.
- Nginx and Caddy mounts remain aligned and read-only.
- Every long-running service has bounded Docker `json-file` retention (`10m` × 3 files).
- Bot, scheduler, and API production containers select the production logging defaults.
- The extracted Jenkins smoke script runs against a fake curl function in an isolated temporary directory: expected admin HTTP 200 must reach the frontend WebSocket on port 8080; HTTP 401/500 login must fail the gate. No deployment host is contacted.

## Usage

```powershell
.venv\Scripts\python.exe -m unittest tests.test_compose_configuration
```

## Dependencies and side effects

Uses PyYAML to parse both Compose files. The tests are read-only and do not require a running Docker daemon.

## Maintenance notes

When intentionally adding a production-only service, update the explicit topology assertion and document why it cannot run locally. Do not weaken the log-retention assertion for long-running services.

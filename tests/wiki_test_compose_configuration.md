# `test_compose_configuration.py`

## Purpose

Protects the intentional relationship between the local and production Docker Compose stacks without introducing a separate `compose.dev` file.

## Coverage

- Both stacks expose the same shared services; the credentials-backed egress proxy is the only production-only service.
- Nginx and Caddy mounts remain aligned and read-only.
- Every long-running service has bounded Docker `json-file` retention (`10m` × 3 files).
- Bot, scheduler, and API production containers select the production logging defaults.

## Usage

```powershell
.venv\Scripts\python.exe -m unittest tests.test_compose_configuration
```

## Dependencies and side effects

Uses PyYAML to parse both Compose files. The tests are read-only and do not require a running Docker daemon.

## Maintenance notes

When intentionally adding a production-only service, update the explicit topology assertion and document why it cannot run locally. Do not weaken the log-retention assertion for long-running services.

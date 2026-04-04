# TODO

Last updated: 2026-04-04

## P0 - Security

- [x] Enforce Studio project ownership checks on all `project_id` endpoints (`studio_router.py`)
- [x] Restrict stats/admin routes with explicit admin dependency (`stats_router.py`)
- [x] Restrict `/ws/users/{user_id}` stream to self or admin (`ws_router.py`)
- [x] Fix privilege escalation in `/auth/register` (new users should not become admin)
- [x] Remove JWT fallback secret in `auth.py`; fail startup if `JWT_SECRET_KEY` is missing
- [x] Add authorization tests for Studio ownership and websocket user stream

## P1 - Reliability

- [x] Fix `scheduler_app/config.py` missing `import logging`
- [x] Fix `scheduler_app/main.py` shutdown path using out-of-scope `scheduler`
- [x] Add graceful shutdown for scheduler health server runner/site

## P1 - Dependencies and Packaging

- [x] Clean `requirements.txt` (duplicates, unpinned libs, inconsistent naming)
- [x] Decide strategy for `matplobbot-shared` pinning and align with `version_bumper.py`
- [x] Add reproducible lock strategy (`pip-tools`/lockfile or equivalent)

## P1 - CI/CD Quality Gates

- [x] Add mandatory validation stage before auto-version and publish:
- [x] Add lint checks
- [x] Add unit/integration tests
- [x] Add type checks
- [x] Block image publish/deploy when validation fails

## P1 - Deployment Hardening

- [ ] Remove source bind mounts from `docker-compose.prod.yml` for API container
- [ ] Replace root SSH deploy in Jenkins with least-privileged deploy user
- [ ] Remove `StrictHostKeyChecking=no` and manage known hosts securely
- [ ] Replace aggressive `docker system prune --all --force` with safer cleanup policy

## P2 - Performance and Scalability

- [ ] Stop fetching Telegram avatars on every update in bot middleware; cache or throttle
- [ ] Reduce stats websocket polling pressure (event-driven updates or adaptive polling)
- [ ] Reuse long-lived aiohttp sessions where possible (e.g. schedule router)

## P2 - Task Sandbox Hardening

- [ ] Replace `ZipFile.extractall()` for build cache with validated safe extraction
- [ ] Strengthen file path validation in project compilation flow (`shared_lib/tasks.py`)

## P2 - Project Tooling

- [x] Add `pyproject.toml` with lint/test/type tool config
- [x] Add pre-commit hooks
- [ ] Add security scan step (`pip-audit`/Bandit or equivalent)

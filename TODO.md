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

- [x] Remove source bind mounts from `docker-compose.prod.yml` for API container
- [ ] Replace root SSH deploy in Jenkins with least-privileged deploy user (infra: requires Jenkins credential/user rotation)
- [x] Remove `StrictHostKeyChecking=no` and manage known hosts securely
  - partial: host keys are currently learned via `ssh-keyscan` during deploy (TOFU). For stronger security, pin a trusted host key/fingerprint in Jenkins credentials.
- [x] Replace aggressive `docker system prune --all --force` with safer cleanup policy
  - partial: Jenkins deploy cleanup is now scoped (`image/container prune` with age filters). Build job still uses `docker system prune -f`.

## P2 - Performance and Scalability

- [x] Stop fetching Telegram avatars on every update in bot middleware; cache or throttle
- [x] Reduce stats websocket polling pressure (event-driven updates or adaptive polling)
- [ ] Reuse long-lived aiohttp sessions where possible (e.g. schedule router) (deferred: requires lifecycle-managed shared session wiring)

## P2 - Task Sandbox Hardening

- [x] Replace `ZipFile.extractall()` for build cache with validated safe extraction
- [x] Strengthen file path validation in project compilation flow (`shared_lib/tasks.py`)

## P2 - Project Tooling

- [x] Add `pyproject.toml` with lint/test/type tool config
- [x] Add pre-commit hooks
- [x] Add security scan step (`pip-audit`/Bandit or equivalent)

## P1 - CI/CD and Release Robustness

- [x] Upgrade GitHub Actions versions in `ci-cd.yml` to Node24-ready majors (`actions/checkout`, `actions/setup-python`, `docker/*` actions)
- [x] Replace `docker system prune -f` in build jobs with scoped/age-filtered cleanup (align with Jenkins safer policy)
- [x] Add CI preflight check to enforce one shared version source (`setup.py` version must match all `matplobbot-shared==...` pins)
- [x] Make PyPI publish step idempotent (`twine upload --skip-existing`) and decide whether publish failure should block pipeline
  - decision: keep pipeline blocking for real publish failures; ignore only "already exists" conflicts via `--skip-existing`.
- [x] Add a CI regression check that base/service Dockerfiles do not attempt to install `matplobbot-shared` from PyPI

## P1 - Deployment Safety and Monitoring

- [ ] Pin a trusted SSH host key/fingerprint in Jenkins credentials (replace TOFU `ssh-keyscan` trust model)
- [ ] Add post-deploy smoke checks (API health, scheduler health, dashboard stats/leaderboard endpoint) and fail deployment on unhealthy state
- [ ] Add deployment failure notification (Telegram/email/webhook) with stage and error snippet

## P2 - Test Coverage Expansion

- [ ] Add integration tests for admin stats/leaderboard data flow (API response contract + empty/error states)
- [ ] Add auth flow tests (`register/login/logout`, JWT expiry, admin/non-admin access matrix)
- [ ] Add tests for `version_bumper.py` (version parsing, replacement validation, failure modes)
- [ ] Add a minimum coverage gate in CI and report trend in PRs

## P2 - Codebase Cleanup

- [ ] Resolve in-code TODO at `bot/handlers/settings.py` (API fallback for settings flow)

## P2 - Functional Improvements (User-Facing)

- [ ] Add plugin-based multi-university support for schedule providers (roadmap item) with provider selection in `/settings`
- [ ] Add voice-driven schedule requests (roadmap item): speech-to-text command path for `/schedule` and `/myschedule`
- [ ] Add unified global search mode that merges `matplobblib` + linked GitHub markdown results with filters
- [ ] Add saved search presets (query + filters) for library/GitHub/schedule searches
- [ ] Add per-subscription notification rules (weekdays, quiet hours, exam-only mode)
- [ ] Add schedule change digest mode (single summary message per day instead of many point updates)
- [ ] Add richer leaderboard functionality (time range switch: day/week/month, command/activity filters)
- [ ] Add "recently viewed" and "continue where I left off" for library/topic browsing
- [ ] Add repository indexing status UI (last indexed time, file count, errors, reindex button)
- [ ] Add onboarding wizard for first-time users (`/start`) to configure language, schedule entity, and notifications
- [ ] Add export options for user stats (JSON and weekly PDF report in addition to CSV)
- [ ] Add localization completeness pass for all user-visible bot and dashboard texts (fill missing RU/EN keys and fallback behavior)

## P2 - Site UI/UX Improvements

- [ ] Add explicit loading/empty/error states for all dashboard widgets (especially leaderboard and charts)
- [ ] Add inline retry actions for failed data blocks (leaderboard, activity feed, user details fetch)
- [ ] Improve mobile responsiveness for dashboard cards/tables (breakpoints, stacking, touch-friendly spacing)
- [ ] Improve table UX: sticky headers, sortable columns, and consistent pagination controls
- [ ] Add visible "last updated" and websocket connection status indicator on live stats pages
- [ ] Preserve filter/sort/date-range state in URL query params for shareable/reload-safe views
- [ ] Add consistent notification pattern (toast/banner) for success, warning, and API failures
- [ ] Improve navigation clarity between Projects/Schedule/Stats pages (active state, breadcrumbs where useful)
- [ ] Add accessibility pass (keyboard navigation, focus states, semantic labels, contrast checks)
- [ ] Add skeleton loaders to reduce layout jumps while data is loading
- [ ] Add quick date-range presets in analytics views (today, 7d, 30d, custom)
- [ ] Add user-facing diagnostics panel for admins (API latency, failed requests count, last sync error)

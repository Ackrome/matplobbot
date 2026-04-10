# TODO

Last updated: 2026-04-10

## Active Backlog (In-Repo)

### P1 - v1.0.0 Release Gate
- [ ] Define `v1.0.0` scope freeze + explicit cut-list ("not in 1.0"), then lock feature creep after RC1.
- [ ] Create a release readiness checklist (Go/No-Go) with required checks: CI green, migrations verified, smoke checks green, rollback tested, docs updated.
- [ ] Prepare a release candidate process (`v1.0.0-rc1`, `rc2`, ...) with acceptance sign-off criteria and owner per check.
- [ ] Add one-command rollback flow for production (restore previous known-good image tags for bot/api/scheduler/worker).
- [ ] Persist and publish "last successful deploy metadata" (image tags + commit SHA + timestamp) to simplify incident rollback.
- [ ] Add production backup policy for Postgres (scheduled `pg_dump`, retention, restore drill) and document RPO/RTO targets.
- [ ] Add migration safety checks in deploy: fail before rollout if alembic revision state is inconsistent; verify post-migration schema health.
- [ ] Add secret scanning in CI (for example `gitleaks`) and block merges on high-confidence leaks.
- [x] Add dependency vulnerability gate in CI (`pip-audit --strict` in CI validate job).
- [ ] Add E2E tests for critical user journeys: auth, schedule search/load, `/myschedule` notifications path, stats export, Studio core actions.
- [ ] Define and enforce a minimum automated coverage target for critical modules (routers/scheduler/studio/stats).
- [ ] Add uptime/error alerts for key production endpoints (`/api/stats/health`, scheduler `/health`, website) with actionable routing to admins.
- [ ] Publish `v1.0.0` operator runbook: deploy, rollback, backup/restore, common incident playbooks, and on-call triage steps.
- [ ] Prepare `v1.0.0` release notes/changelog template with upgrade notes, known limitations, and post-release monitoring checklist.

### P1 - Reliability, Security, and Delivery
- [ ] Escape HTML-sensitive `project.name` before Studio Telegram send (`parse_mode=HTML`) to prevent malformed captions/injection-like rendering; add regression test with `<`, `>`, `&`, and quotes.
- [ ] Add Jenkins pre-deploy quality gate (`python -m unittest` or `pytest` + lint) and fail fast when FastAPI test modules are skipped because dependencies are missing.

### P2 - API and Dashboard

- [ ] Fix `/api/schedule/cached_list` duplicates by returning only latest row per (`entity_type`, `entity_id`) and add API test for stable deduplicated output.
- [ ] Add backend validation for `/api/schedule/search` term length (reject empty/1-char queries) to reduce noisy upstream calls and expensive cache scans.
- [ ] Move CORS allowed origins to env-driven config (`fastapi_stats_app/config.py`) with sane defaults for production and local development.

### P2 - Bot UX
- [x] Add optional "quick set" onboarding step after `/start` for schedule entity + notification time (skip allowed).
- [x] Add `/myschedule` filter presets (for example "only exams", "hide auditorium subscriptions", custom named sets).

### P2 - Quality and Documentation



### P3 back

- [ ] Qdrant for search
- [ ] Add CI matrix run for Python 3.11 and 3.12 to catch version-specific typing/FastAPI regressions earlier.


## Completed In This Iteration

- [x] Fix mojibake RU OpenAPI summary/description text in FastAPI routers to restore readable API docs.
- [x] Expand mojibake cleanup beyond OpenAPI docs: fix corrupted user-facing text in `main_site_frontend` pages/scripts, `studio_router`, and scheduler admin messages.
- [x] add mobile version of auth pages.
- [x] Add test for deterministic ordering in unified schedule search results when mixed entity types return equal match quality.
- [x] Expand encoding guard tests to include website frontend assets (`main_site_frontend/*.html`, `main_site_frontend/js/*.js`) and selected backend user-facing strings.
- [x] Add integration tests for Studio router endpoints (`/api/studio/projects/*`) covering ownership checks, rename conflicts, and Telegram send failure responses.
- [x] Add wiki section describing schedule search offline fallback semantics and `is_offline` flag behavior for frontend maintainers.

## Chosen not to be implemented at all (cuz implemented partially or just don't want)

- [ ] Add per-subscription notification rules (weekdays, quiet hours, exam-only mode).
  - partial: website calendar feed profiles support `exams_only`, but bot schedule subscriptions still only store a single `notification_time`.
- [ ] Add schedule change digest mode (single summary message per day instead of many point updates).
- [ ] Add richer leaderboard functionality (time range switch: day/week/month, command/activity filters).
  - partial: admin stats already have day/week/month activity and command/message filters, and the site stats page has range filtering and sorting, but this is not yet a unified leaderboard feature end-to-end.
- [ ] Add "recently viewed" and "continue where I left off" for library/topic browsing.
  - partial: schedule history and offline cached entities exist, and library favorites exist, but there is no real resume state for library/topic browsing.
- [ ] Add repository indexing status UI (last indexed time, file count, errors, reindex button).
  - partial: repository indexing can already be triggered and logs indexed file counts, but there is no surfaced status UI yet.
- [ ] Add onboarding wizard for first-time users (`/start`) to configure language, schedule entity, and notifications.
  - partial: `/start` already has onboarding with language selection and a feature tour, but it does not yet collect schedule entity or notification preferences.

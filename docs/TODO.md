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
- [ ] Implement Graceful Shutdown: ensure Celery worker waits for active tasks to finish (SIGTERM handling) and FastAPI drains active requests before exiting during deployments.
- [ ] Verify Redis persistence strategy (AOF/RDB) so pending Celery tasks and critical rate-limit states survive container restarts.
- [ ] Enforce strict Rate Limiting (e.g., Token Bucket via Redis) on CPU-intensive endpoints (/api/studio/compile) and bot render commands to prevent OOM/DDoS.
- [ ] Hardcap user inputs: set maximum payload sizes, max execution time for Pandoc/LaTeX, and memory limits inside Celery tasks.
- [ ] Configure Log Rotation (via Docker logging driver or Python's TimedRotatingFileHandler) with size limits and retention policies to prevent disk exhaustion.
- [ ] Create a safe broadcast script/admin command to send the announcements and changelog to all active users with proper rate-limiting (max ~30 msgs/sec for Telegram).

### P1 - Reliability, Security, and Delivery
- [ ] Publish minimal Terms of Service and Privacy Policy on the website and add a /privacy command to the bot.
- [ ] Escape HTML-sensitive `project.name` before Studio Telegram send (`parse_mode=HTML`) to prevent malformed captions/injection-like rendering; add regression test with `<`, `>`, `&`, and quotes.
- [ ] Add Jenkins pre-deploy quality gate (`python -m unittest` or `pytest` + lint) and fail fast when FastAPI test modules are skipped because dependencies are missing.

### P2 - API, Dashboard & Architecture
- [ ] Fix `/api/schedule/cached_list` duplicates by returning only latest row per (`entity_type`, `entity_id`) and add API test.
- [x] Add backend validation for `/api/schedule/search` term length (reject empty/1-char queries).
- [ ] Move CORS allowed origins to env-driven config (`fastapi_stats_app/config.py`).
- [ ] **Rate Limiting:** Add Redis-based rate limiting to heavy endpoints (e.g., PDF rendering, API searches) to prevent abuse.

### P2 - Killer Features & Integrations (The "Cool" Factor)
- [x] **Telegram Mini App (TMA):** Integrate `/schedule` and `/studio` as seamless Web Apps inside Telegram.
- [ ] **Smart OCR:** Accept photos of formulas/boards, convert to LaTeX (via API), and open in Document Studio.
- [x] **PWA Upgrade:** Add a Service Worker to `main_site_frontend` for instant offline loading and mobile app installation.

### P3 - Observability & DevEx
- [x] Add panel on site /stats page with proxy diagnostics summary (e.g. latency per server table).
- [x] Integrate OpenTelemetry for distributed tracing across Bot, FastAPI, and Celery workers.
- [x] Enhance OpenAPI (`/docs`) with full schemas, auth instructions, and custom branding.
- [ ] Add a `Makefile` for streamlined local development and testing workflows.
- [ ] Add CI matrix run for Python 3.11 and 3.12.

### Ideas

- [ ] Feature: OCR for math. Accept photos, convert to LaTeX code, and allow opening in Studio.
- [ ] Integrate OpenTelemetry (Tracing + Metrics) with Jaeger/Grafana to trace requests across FastAPI, Bot, and Celery workers.
- [ ] Upgrade frotend to nfull PWA: Add Service Worker for offline asset caching and "Install App" prompt.
- [ ] User Achievements/Badges system (e.g., "Late Night Coder", "LaTeX Master") displayed in /profile or /stats.
- [ ] Enhance FastAPI OpenAPI docs: Add Markdown descriptions, response schemas, and ReDoc styling.


## Completed In This Iteration

### P2 - Bot UX
- [x] Add optional "quick set" onboarding step after `/start` for schedule entity + notification time (skip allowed).
- [x] Add `/myschedule` filter presets (for example "only exams", "hide auditorium subscriptions", custom named sets).

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
- [ ] Add `/developer_info` command to bot, so it shows Ivan Tishchenko info


## some duplicates, idk. maybe use later



- [ ] **AI Assistant:** Add an "Explain this" inline button for library/GitHub code snippets using LLM API.
- [ ] **Vector Search:** Implement Hybrid Search (Qdrant + BM25) for GitHub notes and Library to improve relevance.

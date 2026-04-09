# TODO

Last updated: 2026-04-09

## Active Backlog (In-Repo)


### P1 - Reliability, Security, and Delivery
- [ ] Escape HTML-sensitive `project.name` before Studio Telegram send (`parse_mode=HTML`) to prevent malformed captions/injection-like rendering; add regression test with `<`, `>`, `&`, and quotes.
- [ ] Add Jenkins pre-deploy quality gate (`python -m unittest` or `pytest` + lint) and fail fast when FastAPI test modules are skipped because dependencies are missing.

### P2 - API and Dashboard

- [ ] Fix `/api/schedule/cached_list` duplicates by returning only latest row per (`entity_type`, `entity_id`) and add API test for stable deduplicated output.
- [ ] Add backend validation for `/api/schedule/search` term length (reject empty/1-char queries) to reduce noisy upstream calls and expensive cache scans.
- [ ] Move CORS allowed origins to env-driven config (`fastapi_stats_app/config.py`) with sane defaults for production and local development.

### P2 - Bot UX
- [ ] Add optional "quick set" onboarding step after `/start` for schedule entity + notification time (skip allowed).
- [ ] Add `/myschedule` filter presets (for example "only exams", "hide auditorium subscriptions", custom named sets).

### P2 - Quality and Documentation
- [ ] Add test for deterministic ordering in unified schedule search results when mixed entity types return equal match quality.
- [ ] Fix mojibake RU OpenAPI summary/description text in FastAPI routers to restore readable API docs.
- [ ] Expand mojibake cleanup beyond OpenAPI docs: fix corrupted user-facing text in `main_site_frontend` pages/scripts, `studio_router`, and scheduler admin messages.
- [ ] Expand encoding guard tests to include website frontend assets (`main_site_frontend/*.html`, `main_site_frontend/js/*.js`) and selected backend user-facing strings.
- [ ] Add integration tests for Studio router endpoints (`/api/studio/projects/*`) covering ownership checks, rename conflicts, and Telegram send failure responses.
- [ ] Add wiki section describing schedule search offline fallback semantics and `is_offline` flag behavior for frontend maintainers.


### P3 back

- [ ] Qdrant for search
- [ ] Add CI matrix run for Python 3.11 and 3.12 to catch version-specific typing/FastAPI regressions earlier.


## Completed In This Iteration

- [x] Add range parameters for user action export (`date_from`, `date_to`, timezone) so weekly PDF and CSV are not fixed to "last 7 days only".
- [x] Add dashboard UI state for API partial degradation (for example when one stats widget fails but others still load).
- [x] Add explicit OpenAPI docs/examples for schedule search `type` aliases (`lecturer`, `teacher`, `room`) to reduce frontend/client ambiguity.
- [x] Add validation/error response for invalid `base_date` format in `GET /api/schedule/data/{type}/{id}` (current path can raise 500 instead of 400/422).
- [x] Define deprecation plan for legacy stats alias `/api/stats/stats/action_users` and remove it after frontend migration window.
 - [x] replace allerts with cool popups
 - [x] Replace hardcoded frontend API hosts (`https://api.ivantishchenko.ru/api`) with a shared configurable base URL (relative `/api` by default + optional override).
 - [x] Localize/fix remaining hardcoded UI text in schedule/auth pages (for example `Full lecturer name`) and replace mojibake symbols like `вЂ”`, `вљ пёЏ`, `вљЎ`.

- [x] Add range parameters for user action export (`date_from`, `date_to`, timezone) so weekly PDF and CSV are not fixed to "last 7 days only".
- [x] Add dashboard UI state for API partial degradation (for example when one stats widget fails but others still load).
- [x] Add explicit OpenAPI docs/examples for schedule search `type` aliases (`lecturer`, `teacher`, `room`) to reduce frontend/client ambiguity.
- [x] Add validation/error response for invalid `base_date` format in `GET /api/schedule/data/{type}/{id}` (current path can raise 500 instead of 400/422).
- [x] Define deprecation plan for legacy stats alias `/api/stats/stats/action_users` and remove it after frontend migration window.

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

# TODO

Last updated: 2026-04-07

## Active Backlog (In-Repo)


### P2 - API and Dashboard
- [ ] Add range parameters for user action export (`date_from`, `date_to`, timezone) so weekly PDF and CSV are not fixed to "last 7 days only".
- [ ] Add dashboard UI state for API partial degradation (for example when one stats widget fails but others still load).
- [ ] Add explicit OpenAPI docs/examples for schedule search `type` aliases (`lecturer`, `teacher`, `room`) to reduce frontend/client ambiguity.
- [ ] Add validation/error response for invalid `base_date` format in `GET /api/schedule/data/{type}/{id}` (current path can raise 500 instead of 400/422).
- [ ] Define deprecation plan for legacy stats alias `/api/stats/stats/action_users` and remove it after frontend migration window.

### P2 - Bot UX
- [ ] Add optional "quick set" onboarding step after `/start` for schedule entity + notification time (skip allowed).
- [ ] Add `/myschedule` filter presets (for example "only exams", "hide auditorium subscriptions", custom named sets).

### P2 - Quality and Documentation
- [ ] Add test for deterministic ordering in unified schedule search results when mixed entity types return equal match quality.
- [ ] Fix mojibake RU OpenAPI summary/description text in FastAPI routers to restore readable API docs.
- [ ] Add wiki section describing schedule search offline fallback semantics and `is_offline` flag behavior for frontend maintainers.

### P3 front
 - [ ] replace allerts with cool popups

### P3 back

- [ ] Qdrant for search
- [ ] Add CI matrix run for Python 3.11 and 3.12 to catch version-specific typing/FastAPI regressions earlier.


## Completed In This Iteration

- [x] Add export options for user stats (JSON and weekly PDF report in addition to CSV).
- [x] Add localization completeness pass for all user-visible bot and dashboard texts (RU/EN keys + fallback behavior).
- [x] Add schedule last parsed time (to both site and bot) to show when it was parsed from university api.
- [x] fix bot subscribtion functionality - so it will give link for filtered schedule with modules that user have chosen before.
- [x] Pin trusted SSH host key/fingerprint in Jenkins credentials by default
- [x] Speed up website schedule unified search by running group/person/auditorium lookups in parallel.
- [x] Fix stats action users endpoint mismatch by exposing `/api/stats/action_users` and keeping legacy `/api/stats/stats/action_users` as compatibility alias.

### P1 - Deployment and Release
- [x] Replace root SSH deploy in Jenkins with least-privileged deploy user
  - blocked/external: needs Jenkins credential rotation + host user provisioning.

### P1 - Reliability and Data Safety
- [x] Persist `/myschedule` filters in DB-backed user settings (not Redis-only 1h TTL) to avoid silent filter resets.
- [x] Add integration test coverage for admin stats endpoints actually used by frontend (`/api/stats/action_users`, profile pagination/sort matrix).

### P1 - Security and Observability
- [x] Add rate limiting and explicit audit metadata for `POST /api/stats/users/{user_id}/send_message` (admin id, target id, timestamp, result).
- [x] Add explicit allowlists for `sort_by` and `sort_order` in stats/profile endpoints to prevent accidental unsafe query paths in future refactors.
- [x] Add per-request correlation id in FastAPI logs and propagate it into scheduler-triggered/admin operations for easier incident tracing.
- [x] Add metrics or counters for schedule API fallback usage (`RUZ API success`, `cache fallback`, `no cache`) to track upstream health.

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
# TODO

Last updated: 2026-04-05

## Active Backlog (In-Repo)

### P1 - Deployment and Release
- [ ] Replace root SSH deploy in Jenkins with least-privileged deploy user
  - blocked/external: needs Jenkins credential rotation + host user provisioning.
- [ ] Pin trusted SSH host key/fingerprint in Jenkins credentials by default
  - partial: pipeline already supports strict fingerprint verification via `DEPLOY_HOST_FINGERPRINT`.

### P2 - Functional Improvements
- [ ] Add unified global search mode that merges `matplobblib` + linked GitHub markdown results with filters.
- [ ] Add saved search presets (query + filters) for library/GitHub/schedule searches.
- [ ] Add per-subscription notification rules (weekdays, quiet hours, exam-only mode).
- [ ] Add schedule change digest mode (single summary message per day instead of many point updates).
- [ ] Add richer leaderboard functionality (time range switch: day/week/month, command/activity filters).
- [ ] Add "recently viewed" and "continue where I left off" for library/topic browsing.
- [ ] Add repository indexing status UI (last indexed time, file count, errors, reindex button).
- [ ] Add onboarding wizard for first-time users (`/start`) to configure language, schedule entity, and notifications.
- [ ] Add export options for user stats (JSON and weekly PDF report in addition to CSV).
- [ ] Add localization completeness pass for all user-visible bot and dashboard texts (RU/EN keys + fallback behavior).

### P2 - Site UI/UX Improvements
- [ ] Improve mobile responsiveness for dashboard cards/tables (breakpoints, spacing, touch targets).
- [ ] Improve table UX (sortable columns + consistent pagination controls).
  - partial: sticky table header is already used on leaderboard.
- [ ] Add visible "last updated" and websocket connection status indicator on live stats pages.
  - mostly done: implemented on dashboard top bar + KPI card timestamp; propagate same pattern to other live pages as needed.
- [ ] Add inline retry actions for failed data blocks (leaderboard, activity feed, user details fetch).
  - partial: retry exists for leaderboard + global stats reconnect + modal user fetch retry.
- [ ] Add consistent notification pattern (toast/banner) for success, warning, and API failures.
  - partial: dashboard now uses toast notifications for websocket/data failures.
- [ ] Preserve filter/sort/date-range state in URL query params for shareable/reload-safe views.
- [ ] Add accessibility pass (keyboard navigation, focus states, semantic labels, contrast checks).
- [ ] Add skeleton loaders to reduce layout jumps while data is loading.
  - partial: leaderboard skeleton rows are shown during websocket (re)connect.
- [ ] Add quick date-range presets in analytics views (today, 7d, 30d, custom).
- [ ] Add user-facing diagnostics panel for admins (API latency, failed request count, last sync error).

## Completed In This Iteration
- [x] Reused long-lived `aiohttp` session for schedule routes via FastAPI lifespan (`app.state.shared_http_session`).
- [x] Updated schedule endpoints to use shared HTTP session instead of per-request session creation.
- [x] Added dashboard websocket connection badge details (status text + last sync timestamp).
- [x] Added widget status handling (loading/empty/error/ok) for leaderboard and chart sections.
- [x] Added inline retry controls for global stats reconnect and modal user-list fetch failures.
- [x] Added dashboard toast notifications for realtime data and connection errors.

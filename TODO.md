# TODO

Last updated: 2026-04-05

## Active Backlog (In-Repo)

### P1 - Deployment and Release
- [ ] Replace root SSH deploy in Jenkins with least-privileged deploy user
  - blocked/external: needs Jenkins credential rotation + host user provisioning.
- [ ] Pin trusted SSH host key/fingerprint in Jenkins credentials by default
  - partial: pipeline already supports strict fingerprint verification via `DEPLOY_HOST_FINGERPRINT`.

### P2 - Functional Improvements
- [x] Add unified global search mode that merges `matplobblib` + linked GitHub markdown results with filters.
- [x] Add saved search presets (query + filters) for library/GitHub/schedule searches.
- [ ] Add per-subscription notification rules (weekdays, quiet hours, exam-only mode).
- [ ] Add schedule change digest mode (single summary message per day instead of many point updates).
- [ ] Add richer leaderboard functionality (time range switch: day/week/month, command/activity filters).
- [ ] Add "recently viewed" and "continue where I left off" for library/topic browsing.
- [ ] Add repository indexing status UI (last indexed time, file count, errors, reindex button).
- [ ] Add onboarding wizard for first-time users (`/start`) to configure language, schedule entity, and notifications.
- [ ] Add export options for user stats (JSON and weekly PDF report in addition to CSV).
- [ ] Add localization completeness pass for all user-visible bot and dashboard texts (RU/EN keys + fallback behavior).
- [ ] Add schedule last parsed time (to both site and bot) to show when it was parsed from university api. 
- [ ] Add toggle "show full lecturer name" in table view of schedule. 
- [ ] Add ical subscription integration to site (only for authorized users)


## Completed In This Iteration
- [x] Add explicit empty-state cards with contextual CTA buttons (retry, reset filters, open docs) for each widget.
- [x] Add table density toggle (compact/default) and persist preference in localStorage.
- [x] Add column visibility controls for leaderboard tables and persist selected columns.
- [x] Add a global command palette (`Ctrl/Cmd+K`) for quick navigation to stats/schedule/studio/admin pages.
- [x] Add keyboard shortcut hints and a help modal (pagination, search focus, refresh, close dialogs).
- [x] Add chart interaction polish: hover crosshair, point tooltips with delta vs previous period, zoom/reset controls.
- [x] Add timezone selector for analytics timestamps and persist per-user preference.
- [x] Add stronger perceived performance: prefetch next leaderboard page and warm up critical API requests on page open.
- [x] Add responsive mobile filter drawer/bottom sheet for date range, sort, and page size controls.
- [x] Add sticky action bar on mobile for common actions (retry, reset filters, open diagnostics).
- [x] Add visual regression safety task: baseline screenshots for stats page (desktop + mobile) in CI.
- [x] Add UI telemetry hooks for UX metrics (time-to-first-data, retries used, failed widget loads) with admin-only dashboard view.
- [x] Ensure navbar coverage and consistency across all pages (active-route highlight, auth-aware links, desktop/mobile parity, and no broken/missing nav entries).
- [x] Improve schedule page information architecture: sticky filter/header zone with clear current context (group, week, date range) and one-click reset.
- [x] Improve schedule page navigation UX: quick jump controls for today/tomorrow/this week/next week.
- [x] Improve schedule page loading UX: skeletons for table/cards and smoother transitions when filters change.
- [x] Improve schedule page mobile UX: larger touch targets, day cards readability, and horizontal overflow handling for timetable grids.
- [x] Improve schedule page empty/error states with actionable CTAs (retry, change group, clear filters).
- [x] Add schedule page personalization UX (remember last selected group/view mode/date range).
- [x] Add explicit UI language toggle (RU/EN) and enforce consistent button labels to prevent mixed Russian/English text on the same screen.

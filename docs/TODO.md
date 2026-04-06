# TODO

Last updated: 2026-04-06

## Active Backlog (In-Repo)

### P1 - Deployment and Release
- [ ] Replace root SSH deploy in Jenkins with least-privileged deploy user
  - blocked/external: needs Jenkins credential rotation + host user provisioning.
- [x] Pin trusted SSH host key/fingerprint in Jenkins credentials by default

### P2 - Functional Improvements

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
- [ ] Add export options for user stats (JSON and weekly PDF report in addition to CSV).
  - partial: the backend already exposes JSON export data for user actions, but the UI still presents CSV export and there is no weekly PDF report.
- [ ] Add localization completeness pass for all user-visible bot and dashboard texts (RU/EN keys + fallback behavior).
  - partial: RU/EN translation loading and fallback behavior already exist, but completeness still needs a pass across all user-visible text.
- [ ] Add schedule last parsed time (to both site and bot) to show when it was parsed from university api.
  - partial: calendar subscription profiles on the site already expose source update time, but the main site schedule view and bot schedule responses do not.


## Completed In This Iteration

- [x] Add proxy to scheduler jobs
- [x] Add toggle "show full lecturer name" in table view of schedule.
- [x] Add ical subscription integration to site (only for authorized users)

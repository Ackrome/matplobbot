# TODO

Last updated: 2026-04-05

## Active Backlog (In-Repo)

### P1 - Deployment and Release
- [ ] Replace root SSH deploy in Jenkins with least-privileged deploy user
  - blocked/external: needs Jenkins credential rotation + host user provisioning.
- [ ] Pin trusted SSH host key/fingerprint in Jenkins credentials by default
  - partial: pipeline already supports strict fingerprint verification via `DEPLOY_HOST_FINGERPRINT`.

### P2 - Functional Improvements

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

- [x] Add proxy to scheduler jobs

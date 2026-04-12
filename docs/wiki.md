# Matplobbot Full Feature Wiki

This page is a full feature map of the project: bot, website, API, scheduler, worker, and delivery pipeline.

## Quick Index

### Bot Features

| Feature | Entry point | Purpose |
| --- | --- | --- |
| [Onboarding and language](#onboarding-and-language) | `/start` | First-run flow, language selection, and guided intro |
| [Help and command menu](#help-and-command-menu) | `/help` | Discover commands and open feature entry points |
| [Library browser and search](#library-browser-and-search) | `/matp_all`, `/matp_search`, `/favorites` | Browse `matplobblib`, search, and manage favorites |
| [GitHub notes browser and search](#github-notes-browser-and-search) | `/lec_all`, `/lec_search` | Browse and search linked GitHub Markdown notes |
| [Unified global search](#unified-global-search) | `/search` | Search library and linked GitHub from one screen |
| [Search presets](#search-presets) | `/search_presets` | Save and rerun search configurations |
| [Schedule discovery](#schedule-discovery) | `/schedule` | Search group/lecturer/room and view day or week schedule |
| [Personal aggregated schedule](#personal-aggregated-schedule) | `/myschedule` | Combined view across active subscriptions with filters |
| [Settings center](#settings-center) | `/settings` | Personal/group settings, subscriptions, short names, privacy |
| [Rendering tools](#rendering-tools) | `/latex`, `/mermaid` | Render formulas and diagrams |
| [Short-name suggestions](#short-name-suggestions) | `/offershorter` | User suggestion flow with admin moderation |
| [Admin commands](#admin-commands) | `/update`, `/clear_cache`, `/send_admin_summary`, `/set_module` | Maintenance and moderation operations |

### Website Features

| Feature | Entry point | Purpose |
| --- | --- | --- |
| [Auth and account sessions](#auth-and-account-sessions) | `/login` + navbar auth actions | Sign in via Telegram or password, persist user profile |
| [Shared navbar and i18n](#shared-navbar-and-i18n) | `main_site_frontend/js/navbar.js` | Cross-page navigation, EN/RU translations, command palette |
| [Schedule page](#schedule-page) | `/schedule` | Unified schedule search, filters, calendar nav, offline awareness |
| [Calendar sync panel](#calendar-sync-panel) | Schedule page calendar section | Manage private iCal feeds and website sync profiles |
| [Stats dashboard](#stats-dashboard) | `/stats` (admin) | Live and REST analytics, degradations, drill-downs |
| [Studio page](#studio-page) | `/studio` | Document compile, project files, exports, send to Telegram |
| [Runtime API base and popup UX](#runtime-api-base-and-popup-ux) | `runtime_config.js`, `ui_utils.js` | Environment-specific API host and unified notifications |

### API Features

| Feature | Entry point | Purpose |
| --- | --- | --- |
| [Auth API](#auth-api) | `/api/auth/*` | Registration, login, Telegram auth, profile, preferences |
| [Schedule API](#schedule-api) | `/api/schedule/*` | Search entities, fetch schedule windows, fallback counters |
| [Stats API](#stats-api) | `/api/stats/*` | Health, profiles, exports, admin messaging, dashboards |
| [Studio API](#studio-api) | `/api/studio/*` | Project CRUD, compile, assets, zip export, Telegram delivery |
| [Calendar API](#calendar-api) | `/api/cal/*` | Authorized calendar config + public iCal feeds |
| [WebSocket API](#websocket-api) | `/ws/*` | Live stats, live log stream, user-specific update stream |

### Background, Data, and Ops

| Feature | Entry point | Purpose |
| --- | --- | --- |
| [Scheduler jobs](#scheduler-jobs) | `scheduler_app/main.py` | Notifications, cache refresh, diffs, cleanup, summaries |
| [Celery worker tasks](#celery-worker-tasks) | `shared_lib/tasks.py` | Rendering and compile pipelines |
| [Cache and fallback model](#cache-and-fallback-model) | Redis + `cached_schedules` | Keep schedule UX available during upstream outages |
| [CI, deploy, and wiki sync](#ci-deploy-and-wiki-sync) | GitHub Actions + Jenkins + `deploy.sh` | Validation, publish/build, production deploy, docs sync |

## Bot Features

### Onboarding And Language

What it does:

- Shows first-start flow with language selector.
- Supports a guided onboarding tour across major bot capabilities.
- Supports language cycling and restart onboarding from settings.
- Adds an optional quick setup step after onboarding to jump directly into schedule subscription setup (`entity + notification time`) with a skip option.

How to use:

1. Send `/start` in private chat.
2. Pick language.
3. Continue onboarding or skip.
4. In the quick setup card, either start immediate schedule setup or skip for now.
5. Open `/settings` to change language later or restart onboarding.

### Help And Command Menu

What it does:

- `/help` presents command-centered navigation.
- Supports private and group-aware help behavior.
- Includes route buttons to major flows (`/schedule`, `/search`, `/search_presets`, etc.).

How to use:

1. Send `/help`.
2. Tap a feature button or run command directly from menu.

### Library Browser And Search

Commands:

- `/matp_all`: interactive browse of indexed `matplobblib` materials.
- `/matp_search`: semantic text search in library content.
- `/favorites`: opens saved favorite materials.

What it does:

- Paginates long result sets.
- Lets users open material by inline result.
- Supports add/remove favorite actions directly from cards.

How to use:

1. Send `/matp_all` to browse by sections.
2. Send `/matp_search`, then enter query text.
3. Use inline result buttons to open, star, or unstar items.
4. Use `/favorites` to revisit saved items.

### GitHub Notes Browser And Search

Commands:

- `/lec_all`: browse linked repositories.
- `/lec_search`: search Markdown chunks in selected linked repository.

What it does:

- Per-user repository management in settings.
- Markdown viewer for selected file chunks.
- Semantic search over configured repo sources.

How to use:

1. Open `/settings` and add a GitHub repo (`owner/repo`) if none linked.
2. Send `/lec_all` to browse notes.
3. Send `/lec_search`, pick a repository, and enter query.

### Unified Global Search

Command:

- `/search`

What it does:

- Merges search across two source types:
- library (`source_type="lib"`)
- linked GitHub repos (`source_type="repo:owner/name"`)
- Supports source toggles and repo subset toggles.
- Uses Redis-backed session state for pagination and result-open callbacks.

How to use:

1. Send `/search`.
2. Toggle sources (Library/GitHub) and optional repos.
3. Send query text.
4. Page through results and open target item.
5. Optionally tap `Save preset`.

### Search Presets

Command:

- `/search_presets`

Supported kinds:

- `library`
- `github`
- `schedule`
- `global`

What it does:

- Saves query + filters (not static result snapshots).
- Stores presets in `User.settings["search_presets"]`.
- Lets users run/delete presets from one menu.

How to use:

1. Run one of supported search flows and get results.
2. Tap `Save preset`, send preset name.
3. Open `/search_presets` later and tap run/delete.

### Schedule Discovery

Command:

- `/schedule`

What it does:

- Search by entity type:
- group
- person (lecturer)
- auditorium
- Shows day view and week view.
- Provides inline calendar navigation.
- Supports iCal export from selected schedule entity.
- Supports subscribe flow with schedule delivery time.

How to use:

1. Send `/schedule`.
2. Pick search type.
3. Enter query and select result.
4. Use day/week/calendar controls.
5. Use subscribe button to set a daily notification time.

### Personal Aggregated Schedule

Command:

- `/myschedule`

What it does:

- Aggregates active subscriptions into one personal timeline.
- Includes filter controls:
- include/exclude subscriptions
- include/exclude lesson types
- Includes filter presets:
- built-in (`All lessons`, `Only exams`, `Hide auditoriums`)
- custom named presets saved from current filter state
- Supports iCal export and personal calendar link actions.
- Includes link revocation action for secret calendar URL.

How to use:

1. Ensure at least one active schedule subscription.
2. Send `/myschedule`.
3. Open `Filters` and apply a built-in preset or save the current filters as a named preset.
4. Toggle per-type/per-source filters and day/week navigation as needed.
5. Export iCal or manage personal calendar link from inline actions.

### Settings Center

Command:

- `/settings` (private and group admin context)

What it does (private):

- Personal display toggles (short names, markdown mode, latex tuning, module details).
- Manage personal schedule subscriptions (list, page, toggle, set time, delete).
- Manage personal short names (create/toggle/delete).
- Manage linked GitHub repositories.
- Restart onboarding.
- Delete my data action.

What it does (group admin):

- Group subscription controls.
- Group language control.
- Admin summary scheduling controls.

How to use:

1. Send `/settings`.
2. Select area (personal, subscriptions, repos, short names, admin/group).
3. Apply changes via inline buttons.

### Rendering Tools

Commands:

- `/latex`
- `/mermaid`

What it does:

- Sends content to worker-backed render tasks.
- Returns rendered output to chat.

How to use:

1. Send `/latex` or `/mermaid`.
2. Send expression/diagram text.
3. Wait for compiled image output.

### Short-Name Suggestions

Command:

- `/offershorter`

What it does:

- Users suggest a shorter discipline alias.
- Admins receive moderation buttons (approve/decline).
- Decision state is persisted to prevent duplicate moderation actions.

How to use:

1. Send `/offershorter`.
2. Enter full discipline and suggested short name.
3. Wait for admin decision.

### Admin Commands

Commands:

- `/update`
- `/clear_cache`
- `/send_admin_summary`
- `/set_module`

What they do:

- Trigger maintenance/cache/index operations.
- Trigger summary delivery.
- Map discipline to module name with `/set_module Discipline | Module`.

How to use:

1. Run command from admin account/chat role.
2. Follow command-specific format prompts.

## Website Features

### Auth And Account Sessions

Pages and scripts:

- `main_site_frontend/login.html`
- `main_site_frontend/register.html`
- `main_site_frontend/js/auth.js`

What it does:

- Supports password login/register.
- Supports Telegram auth handoff.
- Stores bearer token client-side for API calls.
- Loads `/api/auth/me` for profile and role-aware UI.
- Applies shared EN/RU i18n toggle to auth page texts (titles, labels, hints, placeholders, buttons).
- Uses a mobile-optimized auth layout (viewport meta, compact navbar, adaptive spacing for narrow screens).

How to use:

1. Open `/login`.
2. Open `/register` to create an account when needed.
3. Use the navbar `EN/RU` switch to change auth page language.
4. Sign in with Telegram or username/password.
5. After login, navigate to schedule/studio/stats by role.

### Shared Navbar And I18n

Files:

- `main_site_frontend/js/navbar.js`

What it does:

- Shared top nav across pages.
- EN/RU translation dictionary and runtime text updates.
- Command palette and keyboard shortcuts.
- Admin-only nav item for stats page.

How to use:

1. Use language switch in navbar.
2. Open palette/shortcuts from navbar controls.
3. Use account menu for logout and profile actions.

### Schedule Page

Files:

- `main_site_frontend/schedule.html`
- `main_site_frontend/js/schedule.js`
- `main_site_frontend/js/schedule_ux.js`

What it does:

- Unified search for group/lecturer/auditorium.
- Desktop timetable grid + mobile card view.
- Filters and toggles:
- module filters
- short names
- full lecturer name
- Includes copy-to-clipboard actions for room/lecturer.
- Shows source update timestamp and offline/fallback states.
- Persists preference state locally and in account preferences when available.

How to use:

1. Open `/schedule`.
2. Search for group, lecturer, or room.
3. Pick result and switch day/week context.
4. Use filters panel to adjust card/table rendering.

### Calendar Sync Panel

Files:

- `main_site_frontend/js/calendar_sync.js`

What it does:

- Shows eligibility based on Telegram linkage and active bot subscriptions.
- Manages profile-based iCal feeds:
- built-in `All classes`
- built-in `Exams only`
- custom presets from current schedule page
- Supports:
- copy/reveal/hide URL
- Apple/Google/Outlook guidance
- preview and download
- enable/disable sync
- rotate secret
- delete custom preset
- Shows profile health (event count, next event, cache status, source updated, last access).

How to use:

1. Sign in and open `/schedule`.
2. Expand `Calendar subscription`.
3. Select profile and copy or subscribe.
4. Use `Save current view` to create custom profile.
5. Use `Reset link` if URL must be revoked.

### Stats Dashboard

Files:

- `main_site_frontend/stats.html`
- `main_site_frontend/js/stats.js`
- `main_site_frontend/js/stats_ux.js`

What it does:

- Uses REST + WebSocket live updates.
- Displays leaderboard, activity, action distributions, and user drill-down.
- Supports pagination and sorting on user profile/action-users tables.
- Supports exports (JSON/CSV/PDF weekly) with date range and timezone.
- Includes partial-degradation state when one widget fails.

How to use:

1. Sign in as admin.
2. Open `/stats`.
3. Open a user profile from tables/charts.
4. Export user actions in needed format and filter window.

### Studio Page

Files:

- `main_site_frontend/studio.html`
- `main_site_frontend/js/studio.js`

What it does:

- Quick compile mode for text payloads.
- Project mode for multi-file workspaces.
- Supports create/edit/rename/delete files, upload assets, compile, export ZIP.
- Supports sending compiled project PDF directly to linked Telegram account.

How to use:

1. Open `/studio`.
2. Pick quick mode or create project.
3. Edit content, compile, inspect result.
4. Optionally export ZIP or send compiled PDF to Telegram.

### Runtime API Base And Popup UX

Files:

- `main_site_frontend/js/runtime_config.js`
- `main_site_frontend/js/ui_utils.js`

What it does:

- Resolves API base in this order:
- `window.__MPB_API_BASE__`
- `<meta name="mpb-api-base">`
- fallback `/api`
- Shared popup helper `window.mpbPopup(message, options)` replaces raw browser alerts.

How to use:

1. Set runtime override before scripts when needed:

```html
<script>
  window.__MPB_API_BASE__ = "https://api.ivantishchenko.ru/api";
</script>
```

2. Use popup helper from JS modules:

```js
window.mpbPopup("Saved", { type: "success" });
```

## API Features

### Auth API

Router:

- `/api/auth/*`

Endpoints:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/telegram`
- `GET /api/auth/me`
- `POST /api/auth/logout`
- `PUT /api/auth/preferences`

How to use:

1. Authenticate with login or Telegram endpoint.
2. Pass bearer token to protected endpoints.
3. Store/update user preferences through `/preferences`.

### Schedule API

Router:

- `/api/schedule/*`

Endpoints:

- `GET /api/schedule/search`
- `GET /api/schedule/cached_list`
- `GET /api/schedule/fallback_counters` (admin)
- `GET /api/schedule/data/{type}/{id}`

Feature details:

- Search aliases:
- `lecturer` -> `person`
- `teacher` -> `person`
- `room` -> `auditorium`
- For mixed entity types with equal relevance, response ordering is deterministic: `group` -> `person` -> `auditorium`, then stable lexical tie-break by label/id.
- Search automatically falls back to local cache if upstream RUZ fails.
- Schedule data returns:
- `schedule`
- `available_modules`
- `is_offline`
- `source_updated_at`
- `loaded_bounds`

#### Schedule Search Offline Fallback Semantics (Frontend)

What `is_offline` means:

- In `GET /api/schedule/data/{type}/{id}`, `is_offline=true` means live RUZ data was unavailable and the response was assembled from cached schedule data.
- In `GET /api/schedule/search`, `is_offline` is per-result. Mixed responses are possible: some entities may come from live RUZ (`false`) while others are cache fallback (`true`).
- `is_offline=false` means a live upstream response was used for that entity/request path.

Frontend behavior guidance:

1. Keep fallback results selectable and renderable; cache fallback is a degraded-but-valid state, not a hard error.
2. Surface a visible badge/state (for example `CACHE`) when item-level or schedule-level `is_offline=true`.
3. Treat `503` from search as a full-source outage state (upstream unavailable and no cache matches), and show retry/help UI.
4. Use `source_updated_at` together with `is_offline` to communicate data freshness to users.

How to use:

1. Call `/search?term=...&type=all|group|person|auditorium`.
2. Use returned entity `type/id` with `/data/{type}/{id}`.
3. Optionally pass `base_date=YYYY-MM-DD` to center the loaded window.

### Stats API

Router:

- `/api/stats/*`

Endpoints:

- `GET /api/stats/health`
- `GET /api/stats/users/{user_id}/profile` (admin)
- `GET /api/stats/action_users` (admin, canonical)
- `GET /api/stats/stats/action_users` (admin, legacy alias, deprecating)
- `GET /api/stats/users/{user_id}/export_actions` (admin)
- `POST /api/stats/users/{user_id}/send_message` (admin)
- `GET /api/stats/leaderboard` (admin)
- `GET /api/stats/activity` (admin)

Feature details:

- Sort allowlists are strict and validated.
- Export supports `json|csv|weekly_pdf`, `date_from`, `date_to`, `timezone`.
- Admin send-message has Redis-backed per-admin rate limit and structured audit logs.
- Legacy alias can be hard-disabled with `ENABLE_LEGACY_ACTION_USERS_ALIAS=false`.

How to use:

1. Authenticate as admin.
2. Use profile/action drill-down routes for analytics.
3. Use export route for audits/reporting.
4. Use send-message route for direct outreach to Telegram users.

### Studio API

Router:

- `/api/studio/*`

Endpoints:

- `POST /api/studio/compile`
- `GET /api/studio/projects`
- `POST /api/studio/projects`
- `GET /api/studio/projects/{project_id}`
- `PUT /api/studio/projects/{project_id}/files/{file_id}`
- `POST /api/studio/projects/{project_id}/upload`
- `POST /api/studio/projects/{project_id}/compile`
- `DELETE /api/studio/projects/{project_id}/files/{file_id}`
- `PUT /api/studio/projects/{project_id}/files/{file_id}/rename`
- `GET /api/studio/projects/{project_id}/export/zip`
- `GET /api/studio/projects/{project_id}/assets/{file_path}`
- `POST /api/studio/projects/{project_id}/send_telegram`

Feature details:

- Project ownership is enforced on all project routes.
- `upload` supports binary assets up to 5 MB.
- Compile pipeline supports build cache reuse for project compile.

How to use:

1. Create project.
2. Save/edit files and upload assets.
3. Compile and preview.
4. Export ZIP or send compiled PDF to Telegram.

### Calendar API

Routes:

- Authorized profile/config routes under `/api/cal/subscription*`
- Public feed routes under `/api/cal/{secret}*`

Authorized endpoints:

- `GET /api/cal/subscription`
- `POST /api/cal/subscription/reset`
- `POST /api/cal/subscription/toggle`
- `POST /api/cal/subscription/select`
- `POST /api/cal/subscription/profiles`
- `DELETE /api/cal/subscription/profiles/{profile_id}`

Public feed endpoints:

- `GET|HEAD /api/cal/{secret}.ics`
- `GET|HEAD /api/cal/{secret}/basic.ics`
- `GET|HEAD /api/cal/{secret}/profiles/{profile_id}.ics`
- `GET|HEAD /api/cal/{secret}/profiles/{profile_id}/basic.ics`
- `GET|HEAD /api/cal/{secret}/telegram.ics`
- `GET|HEAD /api/cal/{secret}/telegram/basic.ics`

Feature details:

- Profile-based feeds with health metadata.
- `ETag` and `Last-Modified` for cache-aware calendar clients.
- `download=1` forces attachment content disposition.

How to use:

1. Use authorized routes from signed-in website session.
2. Share only secret URLs with trusted calendar clients.
3. Reset secret to revoke leaked links.

### WebSocket API

Endpoints:

- `WS /ws/stats/total_actions`
- `WS /ws/bot_log`
- `WS /ws/users/{user_id}`

Feature details:

- Stats stream sends full live analytics payload when changed.
- Bot log stream replays last lines then tails live file updates.
- User-specific stream is restricted to admins or matching Telegram user.

How to use:

1. Connect with authenticated websocket session/token.
2. Subscribe to needed stream and handle reconnects on disconnect.

## Background, Data, and Operations

### Scheduler Jobs

Source:

- `scheduler_app/main.py`
- `scheduler_app/jobs.py`

Configured jobs:

- `send_daily_schedules` (cron, every minute): sends next-day schedules at subscriber-selected times.
- `check_for_schedule_updates` (interval, every 2h): detects diffs and sends change notifications.
- `update_schedule_cache` (cron at 04:00 and 16:00): warm cache refresh.
- `prune_inactive_subscriptions` (cron at 03:00): cleanup inactive subscriptions.
- `send_admin_summary` (cron, every minute): checks summary schedule and sends due summaries.
- `cleanup_old_log_files` (cron at 04:00): removes old log files.

Other scheduler features:

- Health endpoint on `:9584/health`.
- Telegram calls can use `TELEGRAM_PROXY_URL` with `PROXY_URL` as a backward-compatible fallback.
- RUZ calls are forced direct and bypass proxy.
- Correlation IDs in scheduler logs.

### Bot Startup Reliability

Source:

- `bot/main.py`
- `shared_lib/telegram_http.py`
- `shared_lib/telegram_polling.py`

What it does:

- Uses `TELEGRAM_PROXY_URL` for Telegram-only outbound traffic, with `PROXY_URL` kept as a backward-compatible fallback.
- When `TELEGRAM_PROXY_URL` points to the local Docker `proxy` service on its mixed listener, Telegram traffic is sent through `http://proxy:...` to avoid the SOCKS TLS handshake path.
- Keeps `ruz.fa.ru` out of process-level proxy env via `NO_PROXY`, and creates RUZ aiohttp sessions with `trust_env=False` so schedule fetches stay direct.
- Treats Telegram/proxy transport failures during startup as retryable instead of fatal.
- Recreates the aiogram bot session for each retry so shutdown cleanup from a failed polling attempt does not poison the next one.

How to use:

1. Set `TELEGRAM_PROXY_URL` when Telegram traffic must go through the proxy container.
2. Optionally keep `GLOBAL_HTTP_PROXY_URL` or legacy `PROXY_URL` for other non-RUZ outbound traffic that still needs a process-level proxy.
3. Do not route `RUZ` through proxy; the app now forces direct aiohttp sessions for `ruz.fa.ru`.
4. Optionally set `BOT_POLLING_RETRY_DELAY_SECONDS` to tune the retry backoff.
5. Watch bot logs for `Bot polling failed with a retryable network error` when diagnosing Telegram reachability problems.

### Celery Worker Tasks

Source:

- `shared_lib/tasks.py`

Tasks include:

- LaTeX compile/render.
- Mermaid render.
- Markdown to PDF render.
- Markdown to HTML render.
- Full project compile with build cache.

How to use:

1. Bot/API enqueues task.
2. Worker executes and returns serialized result.
3. Caller sends output to user/UI.

### Cache And Fallback Model

What it does:

- Schedule fetch pipeline prefers live university API.
- Falls back to cached schedule when upstream fails.
- Tracks source outcomes in counters:
- `ruz_api_success`
- `cache_fallback`
- `no_cache`

How to use:

1. Check `GET /api/schedule/fallback_counters` as admin.
2. Correlate spikes in fallback/no-cache with upstream incidents.

### CI, Deploy, And Wiki Sync

CI workflows:

- `.github/workflows/ci-cd.yml`
- `.github/workflows/autolint-autofix.yml`
- `.github/workflows/stats-visual-regression.yml`
- `.github/workflows/sync-wiki.yml`

Pipeline features:

- Lint/test/type/security gates.
- Shared package version consistency checks.
- Auto version patching.
- Shared package publish to PyPI.
- Docker image build/push to GHCR.
- Stats visual baseline capture artifact.
- Wiki sync from `docs/wiki.md` to GitHub Wiki `Home.md`.

Jenkins + deploy features:

- `Jenkinsfile.groovy` performs production deploy and smoke checks.
- Deploy host fingerprint pinning via `APP_VM_SHA256` (with optional one-off override).
- `deploy.sh` performs resilient service-by-service pull with lease-error recovery and retries.

How to use:

1. Push to `main` to run CI and image publishing.
2. Jenkins deploy job pulls tagged images and runs smoke checks.
3. Keep `WIKI_PUSH_TOKEN` configured for automatic wiki mirror updates.

## Practical Notes

- Public calendar links are secrets. Rotate immediately if exposed.
- Legacy stats alias `/api/stats/stats/action_users` is deprecating; migrate clients to `/api/stats/action_users`.
- Website API base can be switched per environment with `window.__MPB_API_BASE__`.
- Bot and website schedule features are intentionally coupled through shared subscription data and cached schedule sources.

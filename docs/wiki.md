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
| [Global dark theme](#global-dark-theme) | public website navbar + `<head>` theme init | Site-wide light/dark mode, persisted per browser |
| [Frontend Tailwind build](#frontend-tailwind-build) | `npm run build:tailwind` | Production CSS generation for static and FastAPI pages |
| [Telegram Mini Apps](#telegram-mini-apps) | Bot Web App buttons + `/schedule`, `/studio` | Launch schedule and Studio inside Telegram with signed auth |
| [PWA install and offline shell](#pwa-install-and-offline-shell) | `site.webmanifest`, `service-worker.js` | Installable frontend with cached app shell |
| [Schedule page](#schedule-page) | `/schedule` | Unified schedule search, filters, calendar nav, offline awareness |
| [Calendar sync panel](#calendar-sync-panel) | Schedule page calendar section | Manage private iCal feeds and website sync profiles |
| [Stats dashboard](#stats-dashboard) | `/stats` (admin) | Live and REST analytics, degradations, drill-downs |
| [Studio page](#studio-page) | `/studio` | Document compile, project files, exports, send to Telegram |
| [Runtime API base and popup UX](#runtime-api-base-and-popup-ux) | `runtime_config.js`, `ui_utils.js` | Environment-specific API host and unified notifications |

### API Features

| Feature | Entry point | Purpose |
| --- | --- | --- |
| [OpenAPI docs](#openapi-docs) | `/docs` | Branded interactive API docs with auth-aware try-it-out |
| [Auth API](#auth-api) | `/api/auth/*` | Registration, login, Telegram auth, profile, preferences |
| [Schedule API](#schedule-api) | `/api/schedule/*` | Search entities, fetch schedule windows, fallback counters |
| [Stats API](#stats-api) | `/api/stats/*` | Health, profiles, exports, admin messaging, dashboards |
| [Studio API](#studio-api) | `/api/studio/*` | Project CRUD, compile, assets, zip export, Telegram delivery |
| [Calendar API](#calendar-api) | `/api/cal/*` | Authorized calendar config + public iCal feeds |
| [WebSocket API](#websocket-api) | `/ws/*` | Live stats, bot-log deprecation notice, user-specific update stream |

### Background, Data, and Ops

| Feature | Entry point | Purpose |
| --- | --- | --- |
| [Scheduler jobs](#scheduler-jobs) | `scheduler_app/main.py` | Notifications, cache refresh, diffs, cleanup, summaries |
| [Container logging and disk limits](#container-logging-and-disk-limits) | `docker-compose*.yml` | Console-only app logs with Docker log rotation |
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
- Supports Telegram Mini App `initData` auth exchange for in-Telegram launches.
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

### Telegram Mini Apps

Files:

- `bot/config.py`
- `bot/keyboards.py`
- `bot/handlers/base.py`
- `main_site_frontend/schedule.html`
- `main_site_frontend/studio.html`
- `main_site_frontend/js/telegram_webapp.js`
- `fastapi_stats_app/auth.py`
- `fastapi_stats_app/routers/auth_router.py`

What it does:

- Adds Telegram Web App launch buttons for `/schedule?tg=1` and `/studio?tg=1` to the bot's private reply/help keyboards.
- Adds `/studio` as a bot command that opens a Web App launch prompt.
- Uses `PUBLIC_SITE_URL` as the public HTTPS base URL for Telegram Web App buttons.
- Adapts `/schedule` and `/studio` to Telegram viewport, safe-area, color scheme, and theme parameters.
- Exchanges signed Telegram Mini App `initData` at `/api/auth/telegram/webapp`, rejects stale signatures by `auth_date`, and stores the returned website JWT.
- Replaces any stale local website JWT inside Telegram with a fresh Mini App token on launch.
- Lets Studio wait for Mini App auth before redirecting to `/login`.

How to use:

1. Set `PUBLIC_SITE_URL` to the public website origin, for example `https://ivantishchenko.ru`.
2. Start or restart the bot so the reply keyboard and `/studio` command are refreshed.
3. In a private Telegram chat, tap `Open Schedule` or `Open Studio`.
4. Use `/schedule?tg=1` or `/studio?tg=1` for direct Mini App testing from Telegram.
5. Keep `BOT_TOKEN` configured in FastAPI; Mini App signed auth is rejected without it.
6. Optionally tune `TELEGRAM_WEBAPP_AUTH_MAX_AGE_SECONDS` if the default 24-hour `auth_date` window is too strict for your deployment.

### PWA Install And Offline Shell

Files:

- `main_site_frontend/site.webmanifest`
- `main_site_frontend/service-worker.js`
- `main_site_frontend/offline.html`
- `main_site_frontend/js/navbar.js`

What it does:

- Makes the static frontend installable with app name, icons, theme colors, start URL, and shortcuts for Schedule and Studio.
- Registers a service worker from shared `navbar.js` on pages that load the common frontend shell.
- Pre-caches the main static pages, shared scripts/styles, icons, Schedule assets, Studio assets, and offline fallback.
- Uses network-first navigation so fresh pages win, then cached pages/offline fallback are used when the network is unavailable.
- Avoids intercepting same-origin `/api/*` requests so authenticated API calls are not cached by the service worker.

How to use:

1. Open the public site over HTTPS.
2. Use the browser install prompt or mobile `Add to Home Screen`.
3. After the first successful online load, reopen `/schedule` or `/studio` from the installed app.
4. If the network is unavailable, cached shell pages load and uncached navigations fall back to `/offline.html`.

### Shared Navbar And I18n

Files:

- `main_site_frontend/js/navbar.js`

What it does:

- Shared top nav across pages.
- EN/RU translation dictionary and runtime text updates.
- Command palette and keyboard shortcuts.
- Sun/moon theme toggle that persists the selected light/dark theme.
- Admin-only nav item for stats page.

How to use:

1. Use language switch in navbar.
2. Use the sun/moon button to toggle the global theme.
3. Open palette/shortcuts from navbar controls.
4. Use account menu for logout and profile actions.

### Global Dark Theme

Files:

- `main_site_frontend/index.html`
- `main_site_frontend/schedule.html`
- `main_site_frontend/studio.html`
- `main_site_frontend/login.html`
- `main_site_frontend/register.html`
- `main_site_frontend/js/theme_bootstrap.js`
- `main_site_frontend/js/navbar.js`
- `main_site_frontend/js/studio.js`

What it does:

- Initializes the preferred theme in `<head>` before page rendering to avoid a light-theme flash.
- Uses Tailwind `darkMode: 'class'`, toggles `html.dark`, and sets `html[data-theme]` for CSS-variable driven surfaces.
- Persists explicit user choice in `localStorage.theme`.
- Falls back to the operating system color scheme when no explicit choice exists.
- Updates shared navbar controls, public pages, schedule rendering, auth pages, Studio chrome, and Monaco editor.
- Updates the current page immediately without rerendering authenticated navbar state.
- Emits `mpb-theme-change` so page-level components can react immediately.

How to use:

1. Open any public site page.
2. Click the sun/moon button next to the language switch.
3. Or open the command palette and run `Toggle theme` / `Переключить тему`.
4. The theme changes immediately; on the next reload the selected theme is applied before the body renders.

### Frontend Tailwind Build

Files:

- `package.json`
- `tailwind.config.js`
- `tailwind.input.css`
- `main_site_frontend/css/tailwind.css`
- `fastapi_stats_app/static/css/tailwind.css`

What it does:

- Builds production Tailwind CSS locally instead of loading `cdn.tailwindcss.com` in the browser.
- Scans static website HTML/JS and FastAPI dashboard templates/JS for utility classes.
- Emits one stylesheet for the nginx-served site and one stylesheet for FastAPI static templates.
- Keeps class-based dark mode enabled for both frontends.

How to use:

1. Run `npm install` after cloning or when dependencies change.
2. Run `npm run build:tailwind` after changing frontend HTML or JS that uses Tailwind utilities.
3. Serve the static site normally; pages load `/css/tailwind.css`.
4. Serve the FastAPI app normally; templates load `/static/css/tailwind.css`.

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

- Shows eligibility based on Telegram linkage. Bot subscriptions are no longer required for website-owned iCal profiles.
- Manages profile-based iCal feeds:
- built-in `All classes`
- built-in `Exams only`
- custom presets from current schedule page
- Stores custom presets in the signed-in user's website preferences, so each account keeps its own presets across reloads and browser sessions.
- Treats custom website profiles as independent calendar sources. Built-in feeds include both active Telegram subscriptions and saved website profiles.
- Warms the semester schedule cache when a website profile is saved, then the background scheduler keeps these web-only sources refreshed.
- Supports:
- expand/collapse panel state
- copy/reveal/hide URL
- Apple/Google/Outlook guidance
- preview and download
- enable/disable sync
- rotate secret
- delete custom preset
- Shows profile health (event count, next event, cache status, source updated, last access).

How to use:

1. Sign in and open `/schedule`.
2. Link the website account to Telegram to generate the private secret link.
3. Expand `Calendar subscription`.
4. Open any group, lecturer, or room schedule and use `Save current view` to create a website-only iCal profile.
5. Select a built-in or custom profile and copy/subscribe to its URL.
6. Use `Reset link` if URL must be revoked.

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
- Follows the global website theme and switches Monaco between `vs-light` and `vs-dark`.

How to use:

1. Open `/studio`.
2. Pick quick mode or create project.
3. Edit content, compile, inspect result.
4. Toggle the site theme from the navbar or command palette when needed.
5. Optionally export ZIP or send compiled PDF to Telegram.

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

### OpenAPI Docs

Entry point:

- `/docs`

Feature details:

- Swagger UI is branded for Matplobbot instead of using the stock FastAPI styling.
- The info block includes auth instructions for both username/password login and Telegram-issued JWTs.
- JSON endpoints expose concrete request/response schemas, while ZIP/PDF/iCal routes document their content types explicitly.
- Protected HTML pages are excluded from the schema so the docs stay API-focused.

How to use:

1. Open `/docs`.
2. For password auth, click `Authorize` and enter website credentials; Swagger UI will fetch a token from `/api/auth/login`.
3. For Telegram auth, call `/api/auth/telegram`, copy `access_token`, then paste that JWT into `Authorize`.
4. Use the schema panels to inspect payload fields before trying schedule, stats, studio, or calendar endpoints.

### Auth API

Router:

- `/api/auth/*`

Endpoints:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/telegram`
- `POST /api/auth/telegram/webapp`
- `GET /api/auth/me`
- `POST /api/auth/logout`
- `PUT /api/auth/preferences`

How to use:

1. Authenticate with login or Telegram endpoint.
2. For Telegram Mini Apps, send raw `window.Telegram.WebApp.initData` as `{ "init_data": "..." }` to `/telegram/webapp`.
3. Pass bearer token to protected endpoints.
4. Store/update user preferences through `/preferences`.

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
- Search terms must contain at least 2 non-whitespace characters; shorter terms return `422`.
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

1. Call `/search?term=...&type=all|group|person|auditorium` with a term of at least 2 non-whitespace characters.
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
- Bot log file streaming is disabled because services no longer write `.log` files.
- User-specific stream is restricted to admins or matching Telegram user.

How to use:

1. Connect with authenticated websocket session/token.
2. Subscribe to needed stream and handle reconnects on disconnect.
3. For service logs, use `docker compose logs -f <service>` instead of `/ws/bot_log`.

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

Other scheduler features:

- Health endpoint on `:9584/health`.
- Telegram calls can use `TELEGRAM_PROXY_URL` with `PROXY_URL` as a backward-compatible fallback.
- Scheduler Telegram delivery uses the same normalized proxy selection as the bot, so the local mixed `proxy` listener is used as `http://proxy:20170` when applicable.
- RUZ calls are forced direct and bypass proxy.
- Correlation IDs in scheduler stdout logs.

### Container Logging And Disk Limits

Source:

- `bot/logger.py`
- `fastapi_stats_app/main.py`
- `scheduler_app/main.py`
- `docker-compose.yml`
- `docker-compose.prod.yml`

What it does:

- Bot, FastAPI, and scheduler logging is console-only through `logging.StreamHandler()`.
- The shared `bot_logs` Docker volume and `/app/logs` mounts are removed.
- Long-running containers use Docker `json-file` log rotation with `max-size=10m` and `max-file=3`.
- Per-container Docker logs are capped at roughly 30 MB for `mpb-telegram-bot`, `mpb-fastapi-stats`, `mpb-worker`, `mpb-scheduler`, `postgres`, and `redis`.
- The `/ws/bot_log` endpoint no longer tails a file and returns an informational message instead.

How to use:

1. Read live logs with `docker compose logs -f mpb-telegram-bot` or another service name.
2. Use `docker compose -f docker-compose.prod.yml logs --tail=200 mpb-fastapi-stats` on production deployments.
3. After deploying this change, remove the old named log volume only after confirming no previous stack still needs it, for example `docker volume rm matplobbot_bot_logs`.
4. Keep the `logging` block on every long-running service that writes useful stdout/stderr output.

### Bot Startup Reliability

Source:

- `bot/main.py`
- `shared_lib/telegram_http.py`
- `shared_lib/telegram_polling.py`

What it does:

- Uses `TELEGRAM_PROXY_URL` for Telegram-only outbound traffic, with `PROXY_URL` kept as a backward-compatible fallback.
- `TELEGRAM_PROXY_TRANSPORT` controls how Telegram reaches the mixed proxy listener:
- `auto`: current default, converts local `socks5://proxy:...` to `http://proxy:...`
- `http`: always prefer HTTP proxy mode
- `socks` or `tcp`: keep SOCKS/TCP mode and do not rewrite the scheme
- When `TELEGRAM_PROXY_URL` points to the local Docker `proxy` service on its mixed listener and transport is `auto`, Telegram traffic is sent through `http://proxy:...` to avoid the aiogram SOCKS TLS handshake path.
- The bot uses a custom aiogram session wrapper so HTTP proxies go through native `aiohttp` request proxying instead of aiogram's `aiohttp_socks` proxy connector.
- The Mihomo proxy now routes by exact target domain instead of catch-all proxying: Telegram domains use `TELEGRAM-AUTO`, OpenAI/ChatGPT domains use `OPENAI-AUTO`, and everything else stays direct.
- The Telegram provider/group health checks probe Telegram directly (`https://api.telegram.org`), and the `TELEGRAM-AUTO` `url-test` group picks the lowest-latency Telegram-capable node instead of just the first alive node.
- The OpenAI provider/group health checks probe `https://api.openai.com/v1/models`, accept `401`/`403` style responses, and the `OPENAI-AUTO` `url-test` group independently picks the lowest-latency OpenAI-capable node.
- The bundled production proxy image pins a current Mihomo core version so modern subscription node formats and Telegram-facing HTTP proxy behavior stay compatible.
- The subscription cleaner preserves more VLESS Reality fields when converting provider JSON to Mihomo YAML, including `servername`, `alpn`, `skip-cert-verify`, `packet-encoding`, `encryption`, and ML-KEM support flags.
- The proxy bootstrap can also use `OUTLINE_ACCESS_KEY` directly, including plain `ss://...` access keys and `ssconf://...` dynamic Outline links that resolve to an access payload.
- The proxy cleaner now merges nodes from both `SUB_URL` and `OUTLINE_ACCESS_KEY` into one served provider document, so Mihomo can choose across the union of Happ subscription nodes and the Outline access key instead of forcing an either/or choice.
- The Outline cleaner emits JSON-escaped YAML scalars for dynamic access keys, so provider values such as Shadowsocks `prefix` strings with CRLF control characters stay valid for Mihomo parsing.
- The proxy keeps localhost and RFC1918 addresses direct so its own subscription refresh path does not recurse back through remote proxy nodes.
- The proxy cleaner now exposes internal diagnostics endpoints on port `8080`: `/health`, `/diagnostics`, `/summary`, and `/recheck?group=telegram|openai|all`.
- The proxy image waits for the local cleaner `/health` endpoint before launching Mihomo, which removes the startup race where Mihomo tried to fetch providers before the cleaner was listening.
- `/diagnostics` reports the last merged-provider build state plus Mihomo controller snapshots for providers and the active Telegram/OpenAI groups.
- `/summary` extracts the practical view you usually need: selected Telegram/OpenAI group member, candidate counts, and the top candidates sorted by the latest known delay.
- `/recheck` triggers Mihomo provider health checks and group delay tests immediately, which the bot now uses before retrying a failed Telegram request.
- Keeps `ruz.fa.ru` out of process-level proxy env via `NO_PROXY`, and creates RUZ aiohttp sessions with `trust_env=False` so schedule fetches stay direct.
- The bot session retries a small number of transport-level Telegram request failures before surfacing an error, which helps when a proxy node briefly resets or times out before the request reaches Telegram.
- The proxy groups probe more aggressively (`interval: 15`, `max-failed-times: 1`, `lazy: false`) so Mihomo re-checks bad nodes quickly after a transport failure instead of waiting through several broken requests.
- Treats Telegram/proxy transport failures during startup as retryable instead of fatal.
- Recreates the aiogram bot session for each retry so shutdown cleanup from a failed polling attempt does not poison the next one.

How to use:

1. Set `TELEGRAM_PROXY_URL` when Telegram traffic must go through the proxy container.
2. Set `TELEGRAM_PROXY_TRANSPORT=tcp` when Telegram should use the mixed listener as SOCKS/TCP instead of HTTP proxy mode.
3. Optionally keep `GLOBAL_HTTP_PROXY_URL` or legacy `PROXY_URL` for other non-RUZ outbound traffic that still needs a process-level proxy.
4. Do not route `RUZ` through proxy; the app now forces direct aiohttp sessions for `ruz.fa.ru`.
5. Optionally set `BOT_POLLING_RETRY_DELAY_SECONDS` to tune the retry backoff.
6. Watch `docker compose logs -f mpb-telegram-bot` for `Bot polling failed with a retryable network error` when diagnosing Telegram reachability problems.
7. If the proxy container has many nodes, keep its health-check target aligned with the real destination (`api.telegram.org`) so Mihomo does not prefer nodes that only pass generic web probes.
8. Rebuild the `proxy` container when `proxy/Dockerfile.proxy` or `proxy/proxy_config.yaml` changes, because the production stack builds that service locally instead of pulling it from GHCR.
9. If your provider ships Xray-style JSON configs, keep the converter in `proxy/proxy_cleaner.py` aligned with the subscription format so Reality and chained dialer settings survive the translation into Mihomo YAML.
10. If your provider gives an Outline link, set `OUTLINE_ACCESS_KEY` alongside `SUB_URL` in `.env` and rebuild the `proxy` service; the cleaner now merges both sources into one provider output instead of choosing one and ignoring the other.
11. Keep the Mihomo rules domain-specific: `api.telegram.org` and related Telegram domains through `TELEGRAM-AUTO`, `chatgpt.com`/`openai.com` domains through `OPENAI-AUTO`, and `MATCH,DIRECT` as the default so unrelated traffic does not consume fragile VPN nodes.
12. If the proxy path is flaky, tune `TELEGRAM_REQUEST_RETRY_ATTEMPTS` and `TELEGRAM_REQUEST_RETRY_DELAY_SECONDS` to retry only transport-level Telegram request failures before a response starts; this reduces failures from brief proxy resets without broadly retrying completed Bot API sends.
13. If you want Mihomo to choose the fastest available provider node for Telegram or OpenAI, keep `TELEGRAM-AUTO` and `OPENAI-AUTO` as `url-test` groups pointed at the real target domains instead of `fallback` groups.
14. Keep `max-failed-times: 1` on the Mihomo `url-test` groups when you want a single failed Telegram/OpenAI request to trigger a quick re-check and push later retries toward another node.
15. If production `.env` is generated by Jenkins, export `PROD_OUTLINE_ACCESS_KEY` there as well; the pipeline now appends it, plus optional `PROD_TELEGRAM_REQUEST_RETRY_ATTEMPTS` and `PROD_TELEGRAM_REQUEST_RETRY_DELAY_SECONDS`, after writing the base `.env`.
16. Use `http://proxy:8080/diagnostics` from another service container or `http://127.0.0.1:8080/diagnostics` inside the proxy container to inspect the merged node pool and Mihomo’s current Telegram/OpenAI group state.
17. Use `http://proxy:8080/summary` for a compact operational view of which Telegram/OpenAI nodes are currently selected and which candidates are next in line by delay.
18. Use `http://proxy:8080/recheck?group=telegram` to force an immediate Telegram-side health recheck when troubleshooting provider failover.
19. The repo includes `scripts/proxy_summary.py`, which fetches `/summary` and prints the merged entry counts plus the top Telegram/OpenAI candidates in a human-readable CLI format.

### Stats Proxy Diagnostics Panel

Source:

- `fastapi_stats_app/routers/stats_router.py`
- `main_site_frontend/stats.html`
- `main_site_frontend/js/stats.js`

What it does:

- Adds an admin diagnostics block on the site `/stats` page that summarizes the proxy cleaner state without leaving the dashboard.
- Fetches `/api/stats/proxy_diagnostics`, which normalizes the proxy cleaner `/summary` response into a stable UI contract.
- Shows the currently selected Telegram and OpenAI nodes, merged node inventory, the summary source URL, and a latency-ranked per-server table.
- Fails softly when the proxy cleaner is unreachable, so the main stats widgets still load while the diagnostics panel shows the upstream error.

How to use:

1. Keep the proxy cleaner reachable from FastAPI at `http://proxy:8080/summary` inside Docker, or set `PROXY_SUMMARY_URL` when the summary endpoint lives elsewhere.
2. Open the site `/stats` page with an admin account and press `Diagnostics`.
3. Read `Telegram selected node` and `OpenAI selected node` first to confirm which Mihomo candidates are active right now.
4. Use the table rows to compare the latest known latency and liveness per candidate server for each route group.
5. If the panel reports `Proxy summary unavailable`, verify the proxy container, then check `/summary` directly or use `scripts/proxy_summary.py`.

### OpenTelemetry Tracing

Source:

- `shared_lib/telemetry.py`
- `shared_lib/celery_app.py`
- `fastapi_stats_app/telemetry.py`
- `bot/tracing.py`

What it does:

- Enables OTLP trace export for FastAPI, the Telegram bot, and Celery workers.
- Creates spans for FastAPI requests, Telegram bot update handling, Celery task publish, and Celery task execution.
- Propagates W3C trace context plus the existing correlation ID through Celery headers so worker traces stay attached to the originating request or bot update.
- Instruments `aiohttp` client requests so outbound Telegram, GitHub, and other HTTP calls appear inside the same trace tree.

How to use:

1. Set `OTEL_ENABLED=true` or provide `OTEL_EXPORTER_OTLP_ENDPOINT` or `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`.
2. Point the exporter at your collector, for example `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`.
3. Optionally set `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_DEPLOYMENT_ENVIRONMENT`, and `OTEL_SERVICE_NAMESPACE` to match your collector and environment conventions.
4. Restart `mpb-fastapi-stats`, `mpb-telegram-bot`, and `mpb-worker` after changing tracing env vars.
5. Look for service names `matplobbot-fastapi`, `matplobbot-bot`, and `matplobbot-worker` in your tracing backend.
6. Use the existing `X-Request-ID` and `[cid=...]` log fields to line up log lines with exported spans during incident analysis.

### Dependency Audit

Source:

- `requirements.in`
- `requirements.txt`
- `setup.py`

What it does:

- Pins `Pillow` to a non-vulnerable release range (`>=12.2.0,<13`) and locks `requirements.txt` to `12.2.0`.
- Keeps CI `pip-audit --strict` green for the currently reported `GHSA-whj4-6x5x-4v2j` advisory.

How to use:

1. If CI reports a new dependency advisory, update the minimum safe version in `requirements.in`.
2. Refresh the lock in `requirements.txt`.
3. Keep `setup.py` aligned for editable/local installs so dev and CI environments do not drift.

### Production Frontend Proxy Startup

Source:

- `main_site_frontend/default.conf`

What it does:

- Uses Docker DNS (`127.0.0.11`) for runtime upstream resolution of `mpb-fastapi-stats`.
- Prevents the frontend Nginx container from crashing on startup when the API container is not yet resolvable during compose boot.

How to use:

1. Keep `/api/cal/*` routed through the internal `mpb-fastapi-stats:9583` upstream.
2. If the upstream service name changes in compose, update `main_site_frontend/default.conf` to match.
3. After changing frontend proxy routing, redeploy `main-site-frontend` so Nginx reloads the updated config.

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
- `deploy.sh` also rebuilds local build services such as `proxy` and restarts config-mounted services such as `main-site-frontend` and `caddy` so repo changes are actually applied in production.

How to use:

1. Push to `main` to run CI and image publishing.
2. Jenkins deploy job pulls tagged images and runs smoke checks.
3. Keep `WIKI_PUSH_TOKEN` configured for automatic wiki mirror updates.

## Practical Notes

- Public calendar links are secrets. Rotate immediately if exposed.
- Legacy stats alias `/api/stats/stats/action_users` is deprecating; migrate clients to `/api/stats/action_users`.
- Website API base can be switched per environment with `window.__MPB_API_BASE__`.
- Bot and website schedule features are intentionally coupled through shared subscription data and cached schedule sources.

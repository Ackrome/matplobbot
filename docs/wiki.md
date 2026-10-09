---
type: Feature Catalog
title: Matplobbot Full Feature Wiki
description: Full feature map for the bot, website, API, scheduler, worker, and delivery pipeline.
resource: /wiki.md
tags: [features, architecture, api, bot, operations]
status: stable
generated: { by: codex/gpt-5, at: "2026-08-11T00:47:31+03:00" }
sources:
  - id: okf-spec
    resource: https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
    title: Open Knowledge Format v0.2 specification
---

# Matplobbot Full Feature Wiki

This page is a full feature map of the project: bot, website, API, scheduler, worker, and delivery pipeline.

This document is an OKF concept inside the [documentation bundle](index.md). It is kept as the global project wiki source and is mirrored to GitHub Wiki by the existing wiki sync workflow.

## Selected Growth Improvements (2026-10-09)

This implementation covers review items 1–7, 13, 20, 23–25, 27, and 34–35.
It adds the following behavior to the existing product. Historical sprint sections
below describe earlier contracts; the refinements in this section take precedence.

### Authentication, account data and search

- Telegram Login Widget verification requires an integer `auth_date`, checks its
  age after signature validation, and rejects expired or future payloads.
  `TELEGRAM_WIDGET_AUTH_MAX_AGE_SECONDS` defaults to 86400 and
  `TELEGRAM_WIDGET_AUTH_CLOCK_SKEW_SECONDS` to 60.
- Login/registration preserve a same-origin `next` path, including query/hash,
  and reject external/protocol-relative redirects. Studio sends unauthenticated
  users through this flow. The signed-in avatar/name card opens `/account` for
  both ordinary users and administrators, on desktop and mobile. Its localized
  tooltip/accessibility label explains "Account and data"; the mobile card also
  shows this subtitle. Account management has no duplicate top-level menu item.
- `GET /api/auth/account/export` downloads owner-scoped JSON with Studio text
  and base64 assets, preferences, linked Telegram data and retained product
  events. Secrets, mailbox message buffers, generated build caches, shared
  indexes and external backups are excluded. The browser adds this account's
  local Studio drafts to the downloaded export.
- `DELETE /api/auth/account` requires `confirmation: "DELETE"` and an owner-bound
  `export_token` from a successful export, valid for 15 minutes. It atomically
  removes the WebAccount and linked Telegram owner, with dependent data removed
  by foreign-key cascades. The UI requires explicit scope acknowledgement and
  clears the current account's browser drafts after success. Other devices,
  external Telegram messages, backups and external logs have separate lifecycles.
- Telegram-only reset is a separate private-chat operation. It preserves a
  linked website account and the minimum identity needed to retain project access.
  Full erasure invalidates old JWTs through database-backed authentication.
  Existing stats WebSockets revalidate before each payload and at most every
  15 seconds while idle; validation has a two-second deadline and fails closed.
- Full erasure also attempts bounded Redis job cleanup, queued task revocation
  and result forgetting. Active workers are not forcibly killed. Transient
  results may remain until their 24-hour expiry but cannot be read by the removed
  account.
- Global/library/GitHub search distinguish available-but-empty, partly
  unavailable and wholly unavailable sources. Cached data can still produce a
  useful partial result. A backend failure is no longer presented as no matches.

### Studio durability and rendering

- A serialized session layer captures file identity with each save. Switching
  documents, building, exporting or sending waits for the pending save. A failed
  save preserves the current editor and blocks the transition; retry is explicit.
  Account-scoped local drafts survive reload and offline failures. Storage quota
  or blocked browser storage produces a warning rather than silently claiming
  that recovery is available.
- The initial editor is a working textarea on desktop and mobile. Monaco upgrades
  it asynchronously while preserving contents. Its AMD loader is isolated in
  `/studio-editor.html`, which uses the same enforcing CSP as Studio. Markdown,
  KaTeX, Mermaid and desktop split layout load only when needed, with pinned
  versions/SRI and retryable failures. Monaco failure leaves the textarea usable.
- `POST /api/studio/jobs` queues a LaTeX/Markdown/Mermaid snippet; `POST
  /api/studio/projects/{id}/jobs` snapshots saved project files. Both return 202
  with a job ID and expiry. `GET /api/studio/jobs/{id}` is owner-scoped and returns
  queued/running/success/error. Reload resumes polling without submitting another
  task. Jobs/results expire after 24 hours; foreign/expired jobs return 404.
- Project type selects the correct worker. LaTeX uses all project files and
  persists incremental build artifacts only while the current source still
  matches the submitted fingerprint. Cache bytes stay internal. Markdown PDF
  and Mermaid PNG builds consume the main text file; auxiliary project assets
  are not bundled by those workers. Existing synchronous routes remain available.
- Studio UI uses the shared RU/EN dictionaries, semantic labels, live status,
  keyboard-accessible mobile tabs, modal focus trapping/return, and visible focus.
  The shared command palette receives the same keyboard/focus treatment. A
  completed preview is marked stale when its source changes.

### Durable schedules and comparison

- Daily messages now use the existing PostgreSQL delivery outbox, with migration
  `f6c7d8e9f0a1` adding `delivery_kind` and `expires_at`. Daily identities combine
  user, entity and target date; overlapping Web/Telegram profiles do not enqueue
  duplicate deliveries. The original scheduled occurrence determines the target
  date, including catch-up after local midnight.
- `SCHEDULE_DAILY_CATCHUP_SECONDS` defaults to six hours and is bounded below
  24 hours. Missed occurrences within that window are replayed; expired messages
  are not sent. A worker abandoned on its final attempt is finalized as failed,
  and attempt fencing prevents a superseded worker from overwriting a newer
  delivery attempt. Telegram's ambiguous acknowledgement can still cause a
  duplicate external message; the outbox is not an exactly-once transport.
- The schedule page compares up to six explicitly chosen groups, lecturers or
  auditoriums for up to 14 days within the currently cached university semester,
  preserving modules/lesson mode when adding the
  currently open schedule. `POST /api/schedule/plan` returns overlaps, common free
  intervals, source checks and completeness. It uses the existing schedule rate
  limit. Timezone is Moscow in the UI and bot. A free interval means no lesson in
  the selected sources, not guaranteed physical room availability.
- Stale, missing or invalid source data makes a comparison incomplete and
  suppresses free-window claims. Known conflicts are still shown with the warning.
  `/plan`, `/conflicts` and `/free` expose the comparison for the private-chat
  user's own active subscriptions over seven days.

### Operational and product outcomes

- Admin-only `GET /api/insights/operations` and `/api/insights/product?days=30`
  feed the expandable panel on Stats. They expose aggregates, not raw account
  events. The panel clears on logout and ignores responses from obsolete sessions.
- Redis heartbeats record attempts, successes, failures and duration for daily
  schedules, source refreshes, change scans, outbox delivery and compilation.
  Unknown, stale and unavailable observations are distinct from success. A last
  cache-write timestamp is explicitly not proof that every schedule is fresh.
  Worker task results with `status: error` count as failed work even when Celery
  completed the Python task. Heartbeat records expire after seven days.
- Scheduler health includes queue/outbox signals. Pending/processing deliveries
  whose age exceeds
  `SCHEDULE_OUTBOX_ALERT_AGE_SECONDS` (default 1800) degrade health, as do stale or
  failed monitored jobs. Historical failed deliveries remain visible as a count;
  they do not make health permanently fail. The worker queue threshold remains
  separately configurable.
- Migration `f7d8e9f0a1b2` adds small allowlisted product events: search outcomes,
  first recorded subscriptions, and asynchronous Studio outcomes. Events contain
  account foreign keys, event names, timestamps and optional deduplication keys;
  no query/document text, names, IP addresses or credentials. These internal
  identifiers make erasure possible; the data is not described as anonymous.
- Events are retained for 90 days with nightly cleanup and account-delete
  cascades. Historical website activity and later linked Telegram activity are
  normalized to one actor during aggregation. A returning account has events on
  two different UTC dates in the selected period. Search success means a completed
  search with results; a successful Studio outcome means the owner opened an
  asynchronous result. These metrics are not a complete website attendance count.
- Jenkins smoke checks now require successful configured admin login plus an
  anonymous access denial. WebSocket upgrade checks target nginx on port 8080
  (and the public URL when configured), rather than the scheduler health port.

### Rollout and verification

Apply both additive Alembic revisions through `alembic upgrade head` before the
updated services begin using them; restart API, scheduler and worker together so
the job/result contract and 24-hour expiry agree. Frontend asset/SW versions were
bumped. Configuration defaults allow existing environments to start without new
secrets. Do not infer that a local implementation has already been deployed.

Regression coverage includes signed login age, account ownership/erasure and
session revocation, partial search failures, catch-up across midnight, exhausted
outbox attempts, interval calculations, serialized saves, resumed jobs and metrics
aggregation. Browser scenarios cover mobile/desktop, RU/EN, simulated save/CDN
failures, actual pinned preview libraries, auth redirects, account export gating,
incomplete planning sources and logout during metric requests. Local controlled
DB/queue doubles do not replace a real PostgreSQL/Celery deployment smoke test.

The Studio offline-cache regression checks the current local script/stylesheet
URLs from both Studio HTML pages against `CORE_ASSETS`, including their version
queries and file existence. Cache generation numbers and local asset revisions
are not hardcoded in the tests. Intentional cache bumps can pass while missing,
unversioned or mismatched resources still fail. Run the authorization guards and
full CI coverage command after changing shared navbar/service-worker versions.

## Sprint 3 P2 Reliability And Security (2026-09-24)

Sprint 3 closes BUG-03, BUG-06, BUG-09, SEC-03, SEC-04, PROD-01, ARCH-01, ARCH-03,
UX-06, and OPS-02.

All Redis consumers now derive their connection from `REDIS_URL`, including password, TLS,
database number, and URL parameters. `REDIS_HOST`, `REDIS_PORT`, and `REDIS_DB` remain the
backward-compatible fallback. Aiogram uses a separate namespaced `RedisStorage` connection with
`BOT_FSM_TTL_SECONDS` (24 hours by default), so in-progress dialogs survive process replacement;
the existing `/cancel` handlers clear both state and data, and shutdown closes the storage pool.

Stats profile misses now remain HTTP 404 while DB failures remain 500. Weekly WeasyPrint exports
retain their Redis rate limit and execute the complete synchronous renderer through
`asyncio.to_thread`, keeping the API event loop responsive. Worker resources resolve from a source
checkout or `/app/bot`, can be overridden with `APP_BOT_DIR` and `APP_TEMPLATES_DIR`, and are
validated on every worker-process start.

Suggestion moderation stores every unique `(chat_id, message_id)` in a transactional Redis set.
A short Redis decision lock makes simultaneous administrator clicks idempotent; the winning
decision updates every stored admin message before deleting the state. Studio-originated HTML is
parsed and emitted through a Telegram HTML allow-list rather than string replacement, preserving
safe formatting while stripping unknown tags, executable link schemes, and unsupported attributes.

Studio now has a dedicated enforcing CSP on `/studio` and `/studio.html`. Static inline scripts,
styles, and HTML event attributes were moved to versioned same-origin assets; third-party library
versions are pinned and carry SRI. The profile explicitly allows Monaco's required evaluated AMD
modules/runtime styles, CDN worker/style/font assets, blob preview frames, and safe preview images,
while `script-src-attr 'none'` blocks injected handlers. Browser QA covers Monaco, Markdown/KaTeX,
Mermaid 9's string render contract, Telegram WebApp, desktop/mobile tab behavior, and artificial
inline payload rejection.

Single-lesson ICS downloads convert fixed Moscow time (UTC+3) into UTC `DTSTART`/`DTEND` values
ending in `Z`, avoiding an invalid `TZID` reference without `VTIMEZONE`. Both Compose definitions
now use the same bounded Celery ping healthcheck. Scheduler `/health` also exposes
`celery_queue_depth` and returns 503 when it reaches `CELERY_QUEUE_ALERT_THRESHOLD` (default 100),
which is the external monitoring signal; Compose `unhealthy` alone does not restart a worker.

## Sprint 2 Reliability Contracts (2026-09-24)

Sprint 2 closes the production-correctness items BUG-01, BUG-02, BUG-04, BUG-05, BUG-07, and
BUG-08.

Schedule delivery now uses the PostgreSQL `schedule_change_deliveries` outbox introduced by
Alembic revision `f5b6c7d8e9f0`. When a schedule transition is detected, recipient rows, the new
cached schedule, and every matching subscription hash are committed in one transaction. Workers
claim ready rows with `FOR UPDATE SKIP LOCKED`; a successful recipient is finalized independently,
while only failed recipients return to the queue with bounded exponential backoff. Telegram sends
also perform short in-request retries for transport errors and honor Telegram `429 retry_after`.
The relevant controls are `TELEGRAM_REQUEST_RETRY_ATTEMPTS`,
`TELEGRAM_REQUEST_RETRY_DELAY_SECONDS`, `SCHEDULE_OUTBOX_MAX_ATTEMPTS`, and
`SCHEDULE_OUTBOX_BASE_DELAY_SECONDS`.

Daily Telegram schedules still prefer a live RUZ response. If that request fails, the scheduler
loads the cache for the exact entity and appends a localized warning containing the last verified
time in the subscription timezone. It skips that entity when no matching cache exists and continues
processing unrelated entities. All application-written `CachedSchedule.updated_at` values are now
aware UTC instants; historical `TIMESTAMP WITH TIME ZONE` rows are not rewritten blindly.

The Stats WebSocket uses the same runtime origin contract as REST: `__MPB_WS_BASE__` can override
it explicitly, otherwise `__MPB_API_BASE__` is converted from HTTP(S) to WS(S) and a trailing
`/api` is removed. Frontend Nginx proxies `/ws/` with Upgrade headers, and the client permits only
one active connection and one reconnect timer. Jenkins post-deploy checks require HTTP `101` both
through port `9584` and `PUBLIC_SITE_URL`.

Jenkins generates the complete production `.env` as one streamed payload, writes a mode-`600`
temporary file on app-vm, atomically renames it, and verifies required key names without printing
values. Studio ZIP downloads send an ASCII `filename` fallback plus an RFC 5987 UTF-8 `filename*`,
so Cyrillic, spaces, and quotes cannot break the response header.

Deployment note: apply Alembic migrations before starting the updated scheduler. A rolling deploy
may run the API first, but schedule-change polling must not use the new code until revision
`f5b6c7d8e9f0` is present.

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
| [Bot calendar sync manager](#bot-calendar-sync-manager) | `/calendar_sync`, `/start calendar_sync` | Manage WebCal link, calendar profiles, and schedule subscriptions in Telegram |
| [Settings center](#settings-center) | `/settings` | Personal/group settings, subscriptions, short names, privacy |
| [Rendering tools](#rendering-tools) | `/latex`, `/mermaid` | Render formulas and diagrams |
| [Short-name suggestions](#short-name-suggestions) | `/offershorter` | User suggestion flow with admin moderation |
| [Admin commands](#admin-commands) | `/update`, `/clear_cache`, `/send_admin_summary`, `/set_module`, `/broadcast_release` | Maintenance and moderation operations |

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
| [Project README page](#project-readme-page) | `/project` | Render the repository introduction, current capabilities and setup instructions |
| [Runtime API base and popup UX](#runtime-api-base-and-popup-ux) | `runtime_config.js`, `ui_utils.js` | Environment-specific API host and unified notifications |

### API Features

| Feature | Entry point | Purpose |
| --- | --- | --- |
| [OpenAPI docs](#openapi-docs) | `/docs` | Branded interactive API docs with auth-aware try-it-out |
| [API CORS and rate limits](#api-cors-and-rate-limits) | FastAPI env + Redis | CORS origin allowlist and abuse limits for heavy routes |
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
- `/matp_search`: PostgreSQL text search in library content (no vector store).
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
- PostgreSQL text search over configured repo sources; the legacy
  `shared_lib/services/semantic_search.py` module name is retained for imports.

How to use:

1. Open `/settings` and add a GitHub repo (`owner/repo`) if none linked.
2. Send `/lec_all` to browse notes.
3. Send `/lec_search`, pick a repository, and enter query.

GitHub repository references accept `owner/repo`, `owner/repo@branch`, or a
GitHub `/tree/<branch>` URL. References without a branch use `main`; the
canonical stored form is `owner/repo@branch`, and indexing, browsing, raw-file
links, and commit lookups all use that branch.

### Unified Schedule Profiles

`user_schedule_subscriptions` is the canonical profile object shared by the
Telegram bot and WebCal UI. It stores the entity, lesson mode, selected
modules, delivery mode, timezone, notification time, and calendar visibility.
Legacy website JSON profiles remain readable while new website profiles are
also persisted in this table. Web changes are applied to every duplicate
subscription for the same entity, and scheduler notifications are deduplicated
to one message per Telegram user/entity. Moscow (`Europe/Moscow`, GMT+3) is the
default; the calendar API exposes GMT±N carousel values. Telegram delivery is
private-message plus iCal/WebCal link, while the Web UI exposes links only.

The calendar API returns `timezone_options` and each profile includes
`timezone`/`timezone_label`, allowing clients to render the timezone carousel
without duplicating timezone rules.

### Admin User Details

Each static `/stats` leaderboard row now has a visible `Подробнее` link and the
whole row is clickable/focusable; both open `/admin-user.html?user_id=…`.
The page uses the existing JWT session and requests the admin-protected
`/api/stats/users/{user_id}/profile` endpoint; non-admin users never receive
the profile data. The older FastAPI `/users/{user_id}` HTML route is admin-only
as well.
After the profile loads, admins see a Telegram-like conversation with inbound
and outbound text bubbles. History is served by the admin-protected
`GET /api/stats/users/{user_id}/messages` endpoint, paginated newest-first, and
the page polls for new messages every ten seconds while visible. The `Reply as
bot` form calls the admin-protected `/api/stats/users/{user_id}/send_message`
endpoint and displays the correlation id returned by the server. The chat stays
hidden when the profile request is rejected. The initial history includes user
text/commands and messages sent from this admin composer; unrelated automatic
bot replies are not retroactively reconstructed from Telegram.

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
- Uses the same interactive freshness policy as the Web schedule page: cache verified within the last 3 minutes is reused, while older data starts one coalesced full-semester RUZ refresh shared across Web and Telegram callers.
- Waits briefly for a live answer, then shows the saved schedule with an explicit background-refresh or cache-fallback notice instead of blocking the bot; duplicate subscriptions for the same entity still cause only one response and one refresh path.
- When that brief wait expires, the bot keeps watching the already running shared refresh and edits the same Telegram message with the checked schedule or confirmed cache-fallback state. This follow-up never starts a second RUZ request.
- Includes filter controls:
- include/exclude subscriptions
- include/exclude lesson types
- Supports a dedicated `Consultation` lesson type in filters. The built-in `Only exams` preset still keeps pre-exam consultations visible.
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

### Bot Calendar Sync Manager

Commands:

- `/calendar_sync`
- `/start calendar_sync`

What it does:

- Opens the Telegram-side manager for the same WebCal sync state used by the website.
- Shows sync enabled/disabled state, selected calendar profile, profile count, active schedule subscription count, and the selected feed URL.
- Lets users open the selected feed, reset the private calendar secret, enable/disable sync, and jump into schedule subscription management.
- Lists built-in and custom calendar profiles, supports selecting and deleting profiles, and creates custom calendar presets from active schedule subscriptions.
- Uses website account preferences linked by Telegram ID, so profiles created in the bot and profiles created on the site share the same `calendar_sync` state.

How to use:

1. Send `/calendar_sync`, or open `https://t.me/matplobbot?start=calendar_sync`.
2. Use `Manage Schedule Subscriptions` to toggle, retime, delete, or edit modules for bot schedule subscriptions.
3. Open `Profiles and presets` to select a built-in feed or create a custom preset from an active subscription.
4. Use `Open selected feed` or copy the shown URL into a calendar app.
5. Use `Reset Link` if the private URL was exposed.

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
- Builds the worker base image on Node 22 and pins `@mermaid-js/mermaid-cli` for stable Mermaid rendering dependencies.

How to use:

1. Send `/latex` or `/mermaid`.
2. Send expression/diagram text.
3. Wait for compiled image output.
4. After changing Mermaid CLI or Node versions, rebuild `matplobbot-base-worker` before rebuilding worker services.

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
- `/broadcast_release`

What they do:

- Trigger maintenance/cache/index operations.
- Trigger summary delivery.
- Map discipline to module name with `/set_module Discipline | Module`.
- Send release announcements/changelog to active users with a hard Telegram rate cap.

How to use:

1. Run command from admin account/chat role.
2. Follow command-specific format prompts.

### Release Broadcasts

Entry points:

- Admin bot command: `/broadcast_release`
- CLI script: `scripts/broadcast_announcement.py`

What it does:

- Builds a plain-text Telegram broadcast from Markdown sources.
- Defaults to `docs/announcement.md` or `docs/ANNOUNCEMENT.md` when present, plus the current changelog (`docs/changelog-from-0.7.1.md`, falling back to `docs/CHANGELOG.md`).
- Targets active users: users with recent actions in the configured window and users with active schedule subscriptions.
- Splits long content into Telegram-safe chunks and sends sequentially with a rate cap of 30 messages per second.
- Defaults to dry-run mode; sending requires an explicit `--execute`.
- Continues after blocked/deleted users and reports failed user IDs/chunks to the admin or CLI output.

How to use the admin command:

1. Run `/broadcast_release` to preview recipients, chunk count, sources, and total Telegram messages.
2. Optionally narrow the rollout:
   `/broadcast_release --user-id 123456 --file docs/announcement.md`
3. Send for real only after reviewing the dry run:
   `/broadcast_release --execute --active-days 180 --rate 25`
4. For staged delivery, add `--limit 100`; for test delivery, repeat `--user-id`.

How to use the script:

1. Dry-run from the repo root:
   `python scripts/broadcast_announcement.py --print-preview`
2. Test one Telegram account:
   `python scripts/broadcast_announcement.py --user-id 123456 --execute`
3. Send to active users:
   `python scripts/broadcast_announcement.py --execute --active-days 180 --rate 25`
4. Add custom sources with repeated `--file` flags; the script requires `BOT_TOKEN` only when `--execute` is used.

## Website Features

### Auth And Account Sessions

Pages and scripts:

- `main_site_frontend/login.html`
- `main_site_frontend/register.html`
- `main_site_frontend/js/auth.js`

What it does:

- Supports password login for already issued accounts.
- Disables public password registration by default; `POST /api/auth/register` returns 403 unless `AUTH_PASSWORD_REGISTRATION_ENABLED=true`.
- When password registration is explicitly enabled for a controlled environment, it creates only `role="user"` accounts, never admin accounts.
- Supports Telegram auth handoff.
- Supports Telegram Mini App `initData` auth exchange for in-Telegram launches.
- Stores bearer token client-side for API calls.
- Loads `/api/auth/me` for profile and role-aware UI.
- Applies shared EN/RU i18n toggle to auth page texts (titles, labels, hints, placeholders, buttons).
- Uses a mobile-optimized auth layout (viewport meta, compact navbar, adaptive spacing for narrow screens).

How to use:

1. Open `/login`.
2. Sign in with Telegram for a normal web session, or use an already issued admin username/password.
3. Use the navbar `EN/RU` switch to change auth page language.
4. After login, navigate to schedule/studio/stats by role.
5. Enable `AUTH_PASSWORD_REGISTRATION_ENABLED=true` only for controlled development or migration scenarios, then disable it again.

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
- Disables Telegram Web App buttons and logs a warning when `PUBLIC_SITE_URL` does not build HTTPS URLs, preventing Telegram `Bad Request: Only HTTPS links are allowed` errors.
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
7. For local `http://localhost:8080` development, use a public HTTPS tunnel or domain before testing Mini App launch buttons in Telegram; otherwise the bot hides those buttons.

### PWA Install And Offline Shell

Files:

- `main_site_frontend/site.webmanifest`
- `main_site_frontend/service-worker.js`
- `main_site_frontend/offline.html`
- `main_site_frontend/js/navbar.js`

What it does:

- Makes the static frontend installable with app name, icons, theme colors, start URL, and shortcuts for Schedule and Studio.
- Registers a service worker from shared `navbar.js` on pages that load the common frontend shell.
- Pre-caches the main static pages, shared scripts/styles, icons, Schedule, Stats, Studio assets, and offline fallback.
- Uses no-cache network-first navigation so fresh pages win, then cached pages/offline fallback are used when the network is unavailable.
- Uses network-first for same-origin JS/CSS assets so deployed frontend fixes are not served stale once before appearing on the next reload.
- Avoids intercepting same-origin `/api/*` requests so authenticated API calls are not cached by the service worker.
- Cached frontend URLs are versioned independently; Studio currently uses `studio.js?v=12` and
  `studio.css?v=1`, while the service worker cache is `mpb-site-v34`. Bump the changed asset URL
  and service-worker cache together whenever cached frontend behavior changes.

How to use: (or not use)

1. Open the public site over HTTPS.
2. Use the browser install prompt or mobile `Add to Home Screen`.
3. After the first successful online load, reopen `/schedule` or `/studio` from the installed app.
4. If the network is unavailable, cached shell pages load and uncached navigations fall back to `/offline.html`.

### Shared Navbar And I18n

Files:

- `main_site_frontend/js/frontend_i18n.js`
- `main_site_frontend/js/navbar.js`
- `main_site_frontend/locales/en.json`
- `main_site_frontend/locales/ru.json`

What it does:

- Shared top nav across pages.
- Loads one shared EN/RU locale source for navbar, schedule, authentication, and stats runtime text.
- Keeps locale dictionaries out of page scripts and applies runtime text updates through `window.mpbI18n`.
- Command palette and keyboard shortcuts.
- Sun/moon theme toggle that persists the selected light/dark theme.
- Admin-only nav item for stats page.

How to use:

1. Use language switch in navbar.
2. Use the sun/moon button to toggle the global theme.
3. Open palette/shortcuts from navbar controls.
4. Use account menu for logout and profile actions.

Maintenance:

1. Add every new key to both locale JSON files and preserve the same `{placeholder}` names.
2. Load `frontend_i18n.js` before `navbar.js` on pages that use the shared API.
3. Run `python -m unittest discover -s tests -p test_localization_completeness.py -v` after locale changes.
4. Advance the service-worker cache version when changing the loader or locale assets.

### Unified Static Frontend

Files:

- `main_site_frontend/`
- `fastapi_stats_app/main.py`

What it does:

- Uses `main_site_frontend` as the only rendered website/dashboard interface.
- Keeps FastAPI focused on REST, WebSocket, OpenAPI, and protected static documentation assets.
- Redirects the authenticated legacy FastAPI root to `/stats` on `PUBLIC_SITE_URL`.
- Redirects the admin-only legacy `/users/{user_id}` route to `/admin-user.html?user_id=...`.
- Removes the obsolete Jinja dashboard templates and their duplicated dashboard JavaScript/CSS.

How to use:

1. Set `PUBLIC_SITE_URL` to the public website origin in deployed FastAPI environments.
2. Link to `/stats` and `/admin-user.html?user_id=...` for new UI flows.
3. Old FastAPI dashboard bookmarks continue through protected HTTP 307 redirects.

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

What it does:

- Builds production Tailwind CSS locally instead of loading `cdn.tailwindcss.com` in the browser.
- Scans the unified static website HTML/JS for utility classes.
- Emits the stylesheet for the nginx-served site.
- Keeps class-based dark mode enabled for the static frontend.

How to use:

1. Run `npm install` after cloning or when dependencies change.
2. Run `npm run build:tailwind` after changing frontend HTML or JS that uses Tailwind utilities.
3. Serve the static site normally; pages load `/css/tailwind.css`.

### Schedule Page

The weekly table uses compact 156 px time rows. Lesson metadata follows the title
with a small fixed gap instead of being pushed to the card bottom. Parallel cards
reserve their width for the lesson type, title and metadata; short off-slot lessons
stack start/end times beside the action button without clipping. Longer classes
still span their actual time interval, and full titles/details remain available
through the lesson dialog. Verify long titles, parallel classes and off-slot times
when changing density; card coordinates and row heights share one scale.

Files:

- `main_site_frontend/schedule.html`
- `main_site_frontend/js/schedule.js`
- `main_site_frontend/js/schedule_state.js`
- `main_site_frontend/js/schedule_api.js`
- `main_site_frontend/js/schedule_filters.js`
- `main_site_frontend/js/schedule_render.js`
- `main_site_frontend/js/schedule_ux.js`

What it does:

- Unified search for group/lecturer/auditorium.
- Opens schedules from shareable URLs such as `/schedule?type=group&id=...&name=...&date=2026-05-04`.
- Keeps a single page state object with entity, date, view mode, selected modules, lesson mode, offline state, and active calendar profile.
- Syncs that state across URL parameters, local/remote preferences, browser history, and visible UI controls.
- Uses a compact schedule shell: entity selector on the left, week navigation in the center, and `Filters and modules` + `Calendar` actions on the right.
- Keeps the three global display toggles (`Short names`, `Full lecturer name`, `Actions`) visible directly under the toolbar instead of burying them in a separate settings block.
- Keeps `Changes`, `Favorite`, and `Copy link` as a compact utility strip next to the view switcher instead of three large text buttons.
- Desktop timetable grid + mobile card view.
- On wide screens, `Table` is now the default Schedule view; URLs omit `view=table` because table is the canonical desktop mode.
- Desktop `Table` has a sticky summary bar, sticky day headers, a high-priority sticky time column, internal horizontal/vertical scrolling, per-day lesson counts, and compact density-aware timeline cards modeled after the Telegram output hierarchy: kind/module first, discipline as the primary text, room and lecturer as secondary metadata.
- Lesson cards include a systematic quick-action strip:
- copy room
- open lecturer schedule
- open room schedule
- download a one-lesson `.ics`
- show only the lesson module
- hide the lesson module
- Lesson actions are controlled by the shared `Actions` toggle in the filter area, so users can keep cells compact or expose inline quick buttons across the whole schedule.
- View density switcher:
- `Cards` for the current rich card feed
- `Compact` for seeing more lessons on one screen
- `Table` for desktop timetable scanning; on narrow/mobile screens it is treated as desktop-only, the page switches to the card feed, and the table button is disabled
- `Exams` for an exam-focused feed with exam filtering enabled
- Filters and toggles:
- module filters
- module search and selected-module counter in the filter header; the search field keeps focus while the module list rerenders
- schedule module presets saved per schedule entity
- calendar presets can reopen a different schedule entity, lesson mode, and module selection directly on `/schedule`
- favorite schedules remain lightweight bookmarks for fast reopening from search/local history; they still remember the selected module set when saved from the currently opened schedule
- quick module actions: only this module, all except this module, reset/all
- amber highlighting for modules that are not present in the currently visible period/mode
- all classes / exams-only lesson mode
- short names
- full lecturer name
- lesson actions visibility toggle shared across table/cards views
- display toggles stay available even when the selected schedule has no module split
- full lecturer-name preference applies to both desktop cells and mobile cards
- Optional `Changes` panel compares the current schedule with the previous local snapshot for the same entity and respects the current week, module filters, and lesson mode.
- The changes panel reports new, cancelled, moved, room-changed, and lecturer-changed lessons plus source parsing time and previous snapshot time.
- Includes copy-to-clipboard actions for room/lecturer.
- When the `Actions` toggle is enabled, lesson cards and timetable cells expose inline quick buttons for room copy, lecturer/room navigation, one-lesson ICS export, and module-only/module-hide actions without opening a per-card accordion.
- In desktop `Table`, the `Actions` toggle shows a compact action launcher inside each timetable cell instead of a full six-button strip. This keeps long lesson titles visible while still exposing room/teacher/calendar/module actions from a small overlay menu.
- Opens from the shared entity cache immediately and automatically revalidates old data against RUZ with stale-while-revalidate semantics.
- Coalesces concurrent viewers of the same group/lecturer/room into one upstream request through a process-local task and Redis lease; a short failure cooldown prevents retry storms during an outage.
- Shows precise source states instead of a generic stale warning: checked live, recently checked cache, checking now, or confirmed cache after a failed check.
- Cancels superseded browser requests when the user switches entities quickly, and silently polls a bounded number of times while a shared refresh is still running.
- Search UX includes recent schedules, favorites, quick type categories, local fuzzy matching, and separate loading/empty/network-error states.
- Offline drawer shows cached schedules, cache update time, and a refresh action for the current schedule. Admin users also see `Refresh full semester`, which force-refreshes the whole current semester cache for the selected schedule entity.
- The offline drawer is rendered as a floating overlay layer above the schedule grid, so opening cached schedules never pushes the timetable or control rows down.
- Highlights exam-like lessons, including `Семинар+зачет` and `Экзамены`, with the dedicated exam color instead of the regular seminar color.
- Treats `Консультации перед экзаменом` as a consultation, not as a mislabeled exam: the page gives it its own consultation badge/color, but still keeps it in `Exams` / `exams-only` views because it is exam-related.
- In desktop `Table` view, lessons whose real begin/end time from the university API no longer fits a single hardcoded slot are rendered proportionally inside the timetable grid instead of disappearing. The card starts and ends inside the matching rows according to the spent fraction of time, and off-slot items get an explicit compact time badge inside the card.
- Module filters start collapsed, but once opened they stay open while toggling modules or typing in module search, so users can select several modules without reopening the panel.
- Site-side schedule normalization treats `Военная подготовка` lessons as the selectable `Военная кафедра` module when the university API provides them as regular lessons without `module`, and canonicalizes older military-module labels to that same website label.
- Desktop `Table` automatically scrolls its internal viewport to the earliest visible lesson start time after each render, and the table viewport is sized to the remaining browser height to avoid dead space below the grid.
- In `Cards`, `Compact`, and `Exams`, schedule days are collapsible sections. The disclosure state works in both the mobile feed and the desktop `Cards` grid: clicking any day header or its arrow expands/collapses it; the relevant day is initially open, while other days stay as compact headers with their lesson count. The expanded/collapsed choice is kept locally for the selected schedule, week, and lesson mode.
- Persists preference state locally and in account preferences when available.
- Frontend schedule code is being split into focused helper modules: `schedule_state.js`, `schedule_api.js`, `schedule_filters.js`, and `schedule_render.js`.

How to use:

1. Open `/schedule`, or open a direct URL with `type`, `id`, `name`, and optional `date`.
2. Use the top-left selector to search for a group, lecturer, or room.
3. Pick a result, then switch week context; the URL updates with the current state.
4. Use the toggle row for `Short names`, `Full lecturer name`, and `Actions`, then open the filter panel to search modules, toggle them, save a module preset, or apply `Only` / `Except` actions from a module chip.
5. Turn on `Actions` when you want inline quick buttons directly inside lesson cells/cards for room copy, lecturer/room navigation, one-lesson ICS export, and module-focused filtering.
6. Use the compact utility strip next to the view switcher: `Changes` (`Изм.`) compares the current schedule with the previous local snapshot, `Favorite` pins the current entity with its selected module set, and `Copy link` shares the exact current view.
7. Use favorites in search/local history when you want pinned entities that reopen fast without switching calendar presets.
8. Pick another non-favorite schedule from search to reset the module filter to all modules available for that schedule.
9. Use `Cards`, `Compact`, `Table`, or `Exams` to choose display density. The choice is saved and reflected in the URL; `Table` is treated as a desktop mode and automatically falls back to cards on phones.
10. In `Table`, read long or off-slot exams by their vertical span inside the grid: the card position shows where the event starts and ends relative to the standard rows, and the compact time chip shows the exact real time when it does not align to the default slot boundaries. On open or after module filtering, the internal table scroll starts at the first visible lesson time for the current week.
11. Turn on `Actions` if you want quick actions in timetable cells. In desktop `Table`, each cell shows a compact action launcher that opens the room/teacher/calendar/module menu above the card without hiding the lesson title.
12. Open the offline drawer to see cached schedules and refresh the current schedule cache. Admin users can also refresh the selected entity's whole semester cache from this drawer; non-admin users do not see that action. It opens above the timetable as an overlay, not as an expanding layout block.

### Calendar Sync Panel

Files:

- `main_site_frontend/js/calendar_sync.js`
- `main_site_frontend/css/calendar_sync.css`
- `main_site_frontend/js/schedule_workspace.js` (focus and scroll lifecycle)

What it does:

- Opens from `Add to calendar`; `/schedule?calendar=1` and Telegram Mini App
  `/schedule?tg=1&calendar=1` links still open it directly.
- Uses a centered 590 px modal on desktop and a full-screen sheet at 600 px and
  below. A 10 px blurred backdrop separates it from the schedule. Opening the
  dialog does not resize the timetable or rearrange its toolbar.
- Locks background scrolling and interaction, keeps keyboard focus inside the
  dialog, includes disclosure summaries in Tab order, and restores focus and
  page scroll on close. Escape, the close button, and the backdrop dismiss it.
- Keeps the first screen focused on source, effective module selection, calendar
  app and one primary action. Apple opens WebCal; Google/Outlook copy the private
  HTTPS subscription URL. Feedback confirms only the action the website can
  observe, never successful subscription by an external app.
- Builds RU/EN profile descriptions from structured fields. Legacy generated
  names containing stale module counts are displayed as the source name; custom
  names are retained. Built-in profiles and Moscow timezone labels are localized.
- `Change selection` exposes modules, lesson mode, timezone, name and current
  filters. Draft module changes require saving; rerenders preserve disclosures,
  scroll and the focused control, including while requests are pending.
- `My subscriptions` contains built-in All classes/Exams only feeds, custom
  profiles and creation from the currently open schedule. Selecting a feed
  changes the calendar selection without navigating the underlying timetable.
  `Open schedule` remains an explicit action for editing another source's modules.
- `Other options and settings` contains one-time ICS download, private URL
  reveal/copy, feed preview, event count, next class, source update time, Telegram
  link, secret rotation, enable/disable and deletion. Destructive actions retain
  their existing confirmations. A downloaded snapshot is labeled as not updating.
- Keeps a close button available during loading, failures, anonymous access and
  Telegram authorization. Errors offer retry; users without Telegram linkage are
  directed to their account. Closing a pending request does not reopen the dialog.
- Uses the existing canonical subscription API and private feed URLs; no schema
  or delivery behavior changes. Website profiles and Telegram schedules continue
  sharing effective filters and timezone. Built-in feeds aggregate their sources.
- Custom profiles warm the semester cache; the scheduler refreshes web-only
  sources. Feeds cover the current/upcoming semester and include parsing time in
  event descriptions. Exams-only feeds include pre-exam consultations.

How to use:

1. Sign in, link Telegram in the account if needed, and open a schedule.
2. Click `Add to calendar`, check the selected source, choose an app and use its
   primary action. Complete the subscription in the external calendar app.
3. Expand `Change selection` to edit a custom profile. For a different source,
   explicitly open its schedule before using the module checklist.
4. Use `My subscriptions` to select another feed or save the current page as a
   new profile. Use `Other options and settings` for downloads and maintenance.


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
- Shows an admin-only `Refresh schedule cache` action that force-runs the full semester cache remap/refresh workflow from `/stats`; non-admin accounts never see the button, and the API still enforces admin access.
- Uses the shared frontend locale JSON for static labels, dynamic REST/WebSocket statuses, module-management statuses, mobile filters, and empty states. Language changes are applied without a page reload.

How to use:

1. Sign in as admin.
2. Open `/stats`.
3. Open a user profile from tables/charts.
4. Export user actions in needed format and filter window.
5. Use `Refresh schedule cache` after semester id changes to remap cached schedule entities and refresh current-semester data immediately.

### Project README Page

`/project` renders the public repository's `README.md` or `README.ru.md` through
GitHub's Contents API, according to the website language. Both documents contain
English/Russian links; on the site they switch the locale without leaving the page.
Marked parses Markdown; DOMPurify sanitizes the result. Relative links and images
resolve against the repository, and headings populate an adaptive table of contents.
The browser reuses separate language caches for ten minutes before revalidation,
offers an explicit refresh, and can retain an older copy when GitHub is unavailable.
A missing Russian file (HTTP 404) falls back to English with a visible notice;
English content never overwrites the Russian cache. Switching language cancels
older requests and ignores late responses.

The README describes the current repository, not a verified production release.
It covers schedule/calendar workflows, Studio recovery and builds, account data,
administration, local Compose startup and explicit password-admin provisioning.
Its interface screenshots in `image/notes/ui/` use demonstration data. The schedule
and calendar captures dated `20261009` show compact lesson cards, the blurred
desktop subscription dialog and its full-screen mobile layout. Each README uses
the matching RU/EN screenshots for these views; versioned filenames avoid reusing
the old images from browser or GitHub image caches. Keep local
paths and heading links valid, and check the page at desktop and mobile widths
when changing document structure or screenshots. Local edits appear on the public
page only after publication to GitHub and a content refresh. Mermaid code fences
are shown as source code by this reader.

### Studio Page

Files:

- `main_site_frontend/studio.html`
- `main_site_frontend/js/studio.js`
- `main_site_frontend/css/studio.css`
- `main_site_frontend/default.conf`

What it does:

- Quick compile mode for text payloads.
- Project mode for multi-file workspaces.
- Supports create/edit/rename/delete files, upload assets, compile, export ZIP.
- Supports sending compiled project PDF directly to linked Telegram account.
- Follows the global website theme and switches Monaco between `vs-light` and `vs-dark`.
- Sanitizes rendered Markdown with pinned DOMPurify before inserting it into the preview DOM.
  The preview uses an explicit tag/attribute allow-list, removes executable URLs and handlers,
  renders failures through `textContent`, and runs Mermaid in strict security mode. The
  sanitizer-unavailable error is available in both shared frontend locales.
- DOMPurify must load before Marked in `studio.html`. When either the sanitizer policy or the
  Studio script changes, bump both the `studio.js` query version and the service-worker cache
  version so installed clients cannot retain the vulnerable preview implementation.
- The Studio response uses an enforcing CSP with `script-src-attr 'none'`. Monaco still requires
  `unsafe-eval` for its AMD modules and runtime style attributes require `style-src 'unsafe-inline'`;
  do not broaden the script policy to `unsafe-inline`. Pinned CDN tags use SRI.

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
- `/redoc`

Feature details:

- Swagger UI is branded for Matplobbot instead of using the stock FastAPI styling.
- ReDoc is available as a styled read-only API reference for schema browsing and sharing.
- The info block includes auth instructions for both username/password login and Telegram-issued JWTs.
- JSON endpoints expose concrete request/response schemas, shared error schemas, validation-error examples, and rate-limit response metadata.
- ZIP/PDF/iCal routes document their content types explicitly.
- Operation descriptions use Markdown sections for auth behavior, schedule fallback semantics, admin exports, Studio compile outputs, and calendar feed behavior.
- Protected HTML pages are excluded from the schema so the docs stay API-focused.

How to use:

1. Open `/docs`.
2. For password auth, click `Authorize` and enter website credentials; Swagger UI will fetch a token from `/api/auth/login`.
3. For Telegram auth, call `/api/auth/telegram`, copy `access_token`, then paste that JWT into `Authorize`.
4. Use the schema panels to inspect payload fields before trying schedule, stats, studio, or calendar endpoints.
5. Open `/redoc` when you need a cleaner reference view with grouped tags, Markdown descriptions, and response schema examples.

### API CORS And Rate Limits

Source:

- `fastapi_stats_app/config.py`
- `fastapi_stats_app/rate_limit.py`
- `fastapi_stats_app/main.py`
- `fastapi_stats_app/routers/schedule_router.py`
- `fastapi_stats_app/routers/studio_router.py`
- `fastapi_stats_app/routers/stats_router.py`

What it does:

- Loads CORS allowed origins from `FASTAPI_CORS_ALLOWED_ORIGINS`, with `CORS_ALLOWED_ORIGINS` as a compatibility fallback.
- Accepts comma, semicolon, or newline separated origins; if unset, the public `ivantishchenko.ru` origins remain the default allowlist.
- Applies Redis fixed-window limits to heavy API routes:
- `GET /api/schedule/search` by client IP.
- `POST /api/studio/compile`, `POST /api/studio/projects/{project_id}/compile`, and `POST /api/studio/projects/{project_id}/send_telegram` by authenticated website user.
- `GET /api/stats/users/{user_id}/export_actions?format=weekly_pdf` by authenticated admin.
- Returns `429` with `Retry-After` when a bucket is exhausted.
- Fails open by default if Redis is briefly unavailable, so the API keeps serving traffic; set `FASTAPI_RATE_LIMIT_FAIL_OPEN=false` to fail closed with `503`.

How to use:

1. Set `FASTAPI_CORS_ALLOWED_ORIGINS=https://example.com,https://api.example.com` in the FastAPI environment when deploying under new domains.
2. Keep Redis reachable from `mpb-fastapi-stats`; the limiter uses the shared Redis backend.
3. Tune limits with `FASTAPI_RATE_LIMIT_SCHEDULE_SEARCH_LIMIT`, `FASTAPI_RATE_LIMIT_STUDIO_COMPILE_LIMIT`, and `FASTAPI_RATE_LIMIT_STATS_PDF_EXPORT_LIMIT`.
4. Tune windows with `FASTAPI_RATE_LIMIT_SCHEDULE_SEARCH_WINDOW_SECONDS`, `FASTAPI_RATE_LIMIT_STUDIO_COMPILE_WINDOW_SECONDS`, and `FASTAPI_RATE_LIMIT_STATS_PDF_EXPORT_WINDOW_SECONDS`.
5. Use `FASTAPI_RATE_LIMIT_ENABLED=false` only for controlled local debugging or load testing.
6. If Redis latency is expected to be high, adjust `FASTAPI_RATE_LIMIT_REDIS_TIMEOUT_SECONDS`; the default is intentionally short to avoid tying up request handlers.

### Auth API

Router:

- `/api/auth/*`

Endpoints:

- `POST /api/auth/register` (disabled by default; controlled by `AUTH_PASSWORD_REGISTRATION_ENABLED`)
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

Token behavior:

- Access tokens are issued and verified with PyJWT using `HS256` only.
- Decoding requires and validates `sub`, `iat`, `nbf`, `exp`, `iss`, and `aud`.
- `JWT_ISSUER` defaults to `matplobbot-api`; `JWT_AUDIENCE` defaults to `matplobbot-web`.
- `JWT_LEEWAY_SECONDS` can allow a small deployment clock skew; the default is strict (`0`).
- Tokens issued before this claims migration are intentionally invalid and users must authenticate again after deployment.

### Schedule API

Router:

- `/api/schedule/*`

Endpoints:

- `GET /api/schedule/search`
- `GET /api/schedule/cached_list`
- `GET /api/schedule/fallback_counters` (admin)
- `GET /api/schedule/data/{type}/{id}`
- `POST /api/schedule/cache/{type}/{id}/refresh_semester` (admin)
- `POST /api/schedule/cache/refresh_all_semester` (admin)

Feature details:

- Search aliases:
- `lecturer` -> `person`
- `teacher` -> `person`
- `room` -> `auditorium`
- Search terms must contain at least 2 non-whitespace characters; shorter terms return `422`.
- For mixed entity types with equal relevance, response ordering is deterministic: `group` -> `person` -> `auditorium`, then stable lexical tie-break by label/id.
- Search automatically falls back to local cache if upstream RUZ fails.
- Search is Redis rate-limited to reduce abusive upstream API fan-out.
- Cached list returns recently cached groups, lecturers, and rooms with `updated_at` so the offline drawer can show data freshness.
- Schedule data returns:
- `schedule`
- `available_modules`
- `is_offline`
- `source_updated_at`
- `source_checked_at`
- `freshness` (`live`, `fresh_cache`, `refreshing`, or `stale_fallback`)
- `refresh_in_progress`
- `cache_age_seconds`
- `content_changed`
- `loaded_bounds`
- Normal schedule opens treat a cache verified in the last 3 minutes as fresh by default. Older data starts one shared full-semester RUZ refresh; the request waits briefly for a fast live answer, otherwise returns the cached window with `freshness=refreshing`.
- `GET /api/schedule/data/{type}/{id}` accepts `refresh=1` for an explicit refresh action even when the cache is still fresh. Automatic week navigation uses the freshness policy rather than forcing another upstream request.
- Interactive source calls use one bounded attempt; scheduler jobs retain their longer retry policy. A first visit with no cache waits longer than a cached visit but returns `503` instead of hanging indefinitely.
- Successful empty RUZ lists are authoritative and remove old lessons. Non-list JSON is rejected as a malformed upstream response and never overwrites cache.
- Schedule data has its own Redis-backed per-client rate limit in addition to per-entity request coalescing.
- If a legacy Schedule URL or local state passes a non-numeric group, lecturer, or auditorium label such as `ПМ23-1` as `{id}`, the API resolves it through live RUZ search before fetching schedule data, so refresh uses the numeric RUZ entity id.
- `POST /api/schedule/cache/{type}/{id}/refresh_semester` is admin-only and forces an immediate current-semester RUZ fetch for one schedule entity. It resolves non-numeric group, lecturer, and auditorium labels to numeric RUZ ids, writes the semester payload to `cached_schedules`, and fails instead of silently serving old cache when the upstream refresh cannot be completed.
- `POST /api/schedule/cache/refresh_all_semester` is admin-only and runs the semester maintenance workflow for cached and subscribed schedule entities: it searches each entity by display name, writes fresh semester data under the current RUZ id, deletes stale cache rows after successful remap, moves active Telegram subscriptions, updates website calendar custom profiles, and returns counters for refreshed, remapped, skipped, and failed entities.

#### Schedule Search Offline Fallback Semantics (Frontend)

What `is_offline` means:

- In `GET /api/schedule/data/{type}/{id}`, `is_offline=true` is the compatibility form of `freshness=stale_fallback`: a live check failed and the response was assembled from cached schedule data.
- In `GET /api/schedule/search`, `is_offline` is per-result. Mixed responses are possible: some entities may come from live RUZ (`false`) while others are cache fallback (`true`).
- `is_offline=false` means a live upstream response was used for that entity/request path.

Frontend behavior guidance:

1. Keep fallback results selectable and renderable; cache fallback is a degraded-but-valid state, not a hard error.
2. Surface a visible badge/state (for example `CACHE`) when item-level or schedule-level `is_offline=true`.
3. Treat `503` from search as a full-source outage state (upstream unavailable and no cache matches), and show retry/help UI.
4. Prefer `freshness` and `source_checked_at` for user-facing copy. `source_updated_at` remains as a compatibility alias.

How to use:

1. Call `/search?term=...&type=all|group|person|auditorium` with a term of at least 2 non-whitespace characters.
2. Use returned entity `type/id` with `/data/{type}/{id}`.
3. Optionally pass `base_date=YYYY-MM-DD` to center the loaded window.
4. Pass `refresh=1` only from an explicit action such as `Refresh cache`; ordinary opens already revalidate old data through the shared freshness policy.

Operator controls:

- `SCHEDULE_ON_OPEN_REFRESH_ENABLED` provides a shared Web and `/myschedule` rollback switch to the legacy six-hour freshness window.
- `SCHEDULE_INTERACTIVE_FRESHNESS_SECONDS`, `SCHEDULE_INTERACTIVE_LIVE_WAIT_SECONDS`, and `SCHEDULE_INITIAL_LIVE_WAIT_SECONDS` tune the shared Web and Telegram freshness and user wait budgets.
- `SCHEDULE_INTERACTIVE_UPSTREAM_TIMEOUT_SECONDS`, `SCHEDULE_REFRESH_LOCK_TTL_SECONDS`, and `SCHEDULE_REFRESH_FAILURE_COOLDOWN_SECONDS` bound upstream and coordination behavior.
- `FASTAPI_RATE_LIMIT_SCHEDULE_DATA_LIMIT` and `FASTAPI_RATE_LIMIT_SCHEDULE_DATA_WINDOW_SECONDS` control per-client data reads.

### Stats API

Router:

- `/api/stats/*`

Endpoints:

- `GET /api/stats/health`
- `GET /api/stats/users/{user_id}/profile` (admin)
- `GET /api/stats/action_users` (admin, canonical)
- `GET /api/stats/stats/action_users` (admin, legacy alias, deprecating)
- `GET /api/stats/users/{user_id}/messages` (admin, paginated Telegram text history)
- `GET /api/stats/users/{user_id}/export_actions` (admin)
- `POST /api/stats/users/{user_id}/send_message` (admin)
- `GET /api/stats/leaderboard` (admin)
- `GET /api/stats/activity` (admin)

Feature details:

- Sort allowlists are strict and validated.
- Export supports `json|csv|weekly_pdf`, `date_from`, `date_to`, `timezone`.
- `weekly_pdf` export is Redis rate-limited and moves the complete synchronous WeasyPrint renderer
  to a worker thread so it does not block the FastAPI event loop.
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
- Worker-backed compile and send-to-Telegram routes share the Studio compile rate limit.

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
- `PATCH /api/cal/subscription/profiles/{profile_id}`
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

- Stats stream sends full live analytics payload when changed and therefore requires an admin
  role before the server accepts the connection. Authenticated non-admin accounts are closed
  with WebSocket policy-violation code `1008` and receive no payload.
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

- `send_daily_schedules` (cron, every minute): sends next-day schedules at subscriber-selected times and uses an explicitly timestamped, entity-matched DB cache fallback when RUZ is unavailable.
- `check_for_schedule_updates` (interval, every 2h): detects diffs, atomically records per-user outbox deliveries with the new cache/hash checkpoint, retries only unsent recipients, and refreshes `cached_schedules.updated_at` after every successful unchanged API poll for subscribed entities.
- `deliver_pending_schedule_change_notifications` (interval, every minute): claims ready outbox rows and applies per-recipient retry/backoff without waiting for the next two-hour RUZ poll.
- `refresh_schedule_entity_ids` (cron Sunday 02:30): searches cached/subscribed schedule entities by name to resolve current semester RUZ ids, moves stale subscription/calendar references, and refreshes current-semester cache.
- `update_schedule_cache` (cron at 04:00 and 16:00): warm cache refresh.
- `prune_inactive_subscriptions` (cron at 03:00): cleanup inactive subscriptions.
- `send_admin_summary` (cron, every minute): checks summary schedule and sends due summaries.

Other scheduler features:

- Health endpoint on `:9584/health`; it checks PostgreSQL, scheduler state, and the Redis `celery`
  queue. A queue depth at or above `CELERY_QUEUE_ALERT_THRESHOLD` returns HTTP 503 for external
  monitoring and includes the measured depth and threshold in JSON.
- Telegram calls can use `TELEGRAM_PROXY_URL` with `PROXY_URL` as a backward-compatible fallback.
- Scheduler Telegram delivery uses the same normalized proxy selection as the bot, so the local mixed `proxy` listener is used as `http://proxy:20170` when applicable.
- RUZ calls are forced direct and bypass proxy.
- Correlation IDs in scheduler stdout logs.
- Semester-wide scheduler jobs use the shared `get_semester_bounds()` helper instead of duplicated date windows, keeping RUZ requests under the upstream date-range limit.

### Container Logging And Disk Limits

Source:

- `shared_lib/logging_config.py`
- `bot/logger.py`
- `fastapi_stats_app/main.py`
- `scheduler_app/main.py`
- `docker-compose.yml`
- `docker-compose.prod.yml`

What it does:

- Bot, FastAPI, and scheduler use one `shared_lib.logging_config` policy and remain console-only through `logging.StreamHandler()`.
- `LOG_LEVEL` accepts `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` (`WARN` and `FATAL` are normalized aliases); invalid values stop startup with a clear configuration error.
- `LOG_FORMAT` accepts `text` or `json`. When it is omitted, `ENVIRONMENT=production` selects one-object-per-line JSON and other environments select readable text.
- Structured records contain UTC timestamp, level, stable service name, logger, message, correlation ID, and source location. Existing Uvicorn access/error handlers receive the same formatter.
- The shared `bot_logs` Docker volume and `/app/logs` mounts are removed.
- Long-running containers use Docker `json-file` log rotation with `max-size=10m` and `max-file=3`.
- Per-container Docker logs are capped at roughly 30 MB for the application, database, frontend, Caddy, and production proxy services.
- `docker-compose.yml` is the standalone local stack and `docker-compose.prod.yml` is the standalone production stack used by `deploy.sh`; a separate `compose.dev` file is intentionally not maintained.
- The production credentials-backed `proxy` is the only intentional topology difference. Automated tests enforce shared-service, nginx/Caddy mount, and retention parity.
- The `/ws/bot_log` endpoint no longer tails a file and returns an informational message instead.

How to use:

1. Read live logs with `docker compose logs -f mpb-telegram-bot` or another service name.
2. Use `docker compose -f docker-compose.prod.yml logs --tail=200 mpb-fastapi-stats` on production deployments.
3. Set `LOG_LEVEL=DEBUG` temporarily for diagnosis; set `LOG_FORMAT=json` explicitly when a non-production environment is connected to a structured log collector.
4. After deploying this change, remove the old named log volume only after confirming no previous stack still needs it, for example `docker volume rm matplobbot_bot_logs`.
5. Keep the `logging` block on every long-running service that writes useful stdout/stderr output.

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
- The bundled production proxy image pins Mihomo `v1.19.32` and verifies the official amd64/arm64 archive SHA-256 before installation, so a changed or corrupted release artifact fails the image build.
- The subscription cleaner preserves every supported outbound from Happ/Xray JSON instead of only the last VLESS outbound. VLESS (including WebSocket, gRPC, XHTTP, TLS, and Reality), Hysteria2, Shadowsocks, and SOCKS chains are converted to uniquely named Mihomo nodes.
- Plain and base64-encoded URI bundles are also supported for VLESS, VMess, Trojan, Shadowsocks, Hysteria/Hysteria2, TUIC, AnyTLS, and Mieru. Unknown schemes are skipped and counted in `/diagnostics`; Mihomo does not document a Naive outbound, so `naive://` entries are intentionally reported as unsupported instead of being translated incorrectly.
- XHTTP conversion preserves the documented transport fields and XMUX reuse settings. TLS certificate verification remains enabled unless the source explicitly sets `allowInsecure`/`insecure`.
- The proxy bootstrap can also use `OUTLINE_ACCESS_KEY` directly, including plain `ss://...` access keys and `ssconf://...` dynamic Outline links that resolve to an access payload.
- The proxy cleaner merges legacy `SUB_URL`, all URLs from an owner-readable JSON file outside Git, and `OUTLINE_ACCESS_KEY` into one served provider document. Exact duplicate URLs and duplicate downloaded payloads are ignored, and diagnostics identify sources only as `source-N` so bearer URLs never enter application logs.
- Subscription sources are downloaded in parallel. The cleaner serves the last valid mode-`0600` provider cache immediately, refreshes it atomically in the background, and asks Mihomo to reload both providers after a successful refresh; a slow or unavailable legacy source therefore no longer blocks both provider startup requests.
- Imported legacy Clash YAML is normalized from JSON UTF-16 surrogate escapes to real UTF-8 and maps legacy `obfs-local` option names to Mihomo fields. URI conversion also preserves boolean plugin options such as `v2ray-plugin;mux=0` as booleans rather than invalid strings.
- The Outline cleaner emits JSON-escaped YAML scalars for dynamic access keys, so provider values such as Shadowsocks `prefix` strings with CRLF control characters stay valid for Mihomo parsing.
- The proxy keeps localhost and RFC1918 addresses direct so its own subscription refresh path does not recurse back through remote proxy nodes.
- The proxy cleaner now exposes internal diagnostics endpoints on port `8080`: `/health`, `/diagnostics`, `/summary`, and `/recheck?group=telegram|openai|all`.
- The proxy image waits for the local cleaner `/health` endpoint before launching Mihomo, which removes the startup race where Mihomo tried to fetch providers before the cleaner was listening.
- `/diagnostics` reports the last merged-provider build state plus Mihomo controller snapshots for providers and the active Telegram/OpenAI groups.
- `/summary` extracts the practical view you usually need: selected Telegram/OpenAI group member, candidate counts, and the top candidates sorted by the latest known delay.
- `/recheck` triggers Mihomo provider health checks and group delay tests immediately, which the bot now uses before retrying a failed Telegram request.
- Keeps `ruz.fa.ru` out of process-level proxy env via `NO_PROXY`, and creates RUZ aiohttp sessions with `trust_env=False` so schedule fetches stay direct.
- The bot session retries a small number of transport-level Telegram request failures before surfacing an error, which helps when a proxy node briefly resets or times out before the request reaches Telegram.
- Route groups probe their real destinations every 60 seconds (`max-failed-times: 1`, `lazy: false`), while provider-level checks run every 300 seconds. This avoids continuously flooding Telegram/OpenAI when the merged pool contains hundreds of nodes; the bot can still request an immediate targeted recheck after a transport failure.
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
10. For multiple Happ/provider subscriptions, create `/home/deploy/.config/matplobbot/proxy-subscriptions.json` as `{"urls":["https://provider.example/private-subscription"]}`, owned by the production deploy account with mode `0600` inside a mode-`0700` directory. Keep this bearer-secret file outside Git. Override its host path with `PROXY_SUBSCRIPTIONS_FILE` only when needed; Compose mounts it read-only at `/run/secrets/proxy-subscriptions.json`. Legacy `SUB_URL` and `OUTLINE_ACCESS_KEY` may remain in `.env` and are merged with this file.
11. Keep the Mihomo rules domain-specific: `api.telegram.org` and related Telegram domains through `TELEGRAM-AUTO`, `chatgpt.com`/`openai.com` domains through `OPENAI-AUTO`, and `MATCH,DIRECT` as the default so unrelated traffic does not consume fragile VPN nodes.
12. If the proxy path is flaky, tune `TELEGRAM_REQUEST_RETRY_ATTEMPTS` and `TELEGRAM_REQUEST_RETRY_DELAY_SECONDS` to retry only transport-level Telegram request failures before a response starts; this reduces failures from brief proxy resets without broadly retrying completed Bot API sends.
13. If you want Mihomo to choose the fastest available provider node for Telegram or OpenAI, keep `TELEGRAM-AUTO` and `OPENAI-AUTO` as `url-test` groups pointed at the real target domains instead of `fallback` groups.
14. Keep `max-failed-times: 1` on the Mihomo `url-test` groups when you want a single failed Telegram/OpenAI request to trigger a quick re-check and push later retries toward another node.
15. If production `.env` is generated by Jenkins, export `PROD_OUTLINE_ACCESS_KEY` there as well; the pipeline includes it, plus optional `PROD_TELEGRAM_REQUEST_RETRY_ATTEMPTS` and `PROD_TELEGRAM_REQUEST_RETRY_DELAY_SECONDS`, in the same atomically installed remote `.env` payload.
16. Use `http://proxy:8080/diagnostics` from another service container or `http://127.0.0.1:8080/diagnostics` inside the proxy container to inspect the merged node pool and Mihomo’s current Telegram/OpenAI group state.
17. Use `http://proxy:8080/summary` for a compact operational view of which Telegram/OpenAI nodes are currently selected and which candidates are next in line by delay.
18. Use `http://proxy:8080/recheck?group=telegram` to force an immediate Telegram-side health recheck when troubleshooting provider failover.
19. The repo includes `scripts/proxy_summary.py`, which fetches `/summary` and prints the merged entry counts plus the top Telegram/OpenAI candidates in a human-readable CLI format.
20. After editing the external JSON file, recreate the proxy (`docker compose -f docker-compose.prod.yml up -d --build --no-deps proxy`) and confirm `/diagnostics` reports the expected source, duplicate-payload, unsupported-protocol, and merged-node counts without exposing subscription URLs.

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
- `fastapi_stats_app/requirements.txt`
- `scheduler_app/requirements.txt`
- `requirements-validation.txt`
- `.github/workflows/ci-cd.yml`
- `.github/workflows/dependency-audit.yml`
- `Jenkinsfile.groovy`
- `scripts/build_audit_requirements.py`
- `setup.py`

What it does:

- Pins `Pillow` to a non-vulnerable release range (`>=12.3.0,<13`) and locks `requirements.txt` to `12.3.0`.
- Pins `python-dotenv` to a non-vulnerable release range (`>=1.2.2,<2`) and locks `requirements.txt` to `1.2.2`.
- Pins `aiogram` to `3.29.1` so the bot and scheduler can use the current `aiohttp 3.14.x` release line without the old `<3.14` resolver cap.
- Pins `aiohttp` to the non-vulnerable `3.14.3` release across bot, scheduler, and shared package metadata. This is the minimum version that clears `PYSEC-2026-3545`; `PYSEC-2026-3546` and `PYSEC-2026-3547` are fixed by `3.14.2`, but the lock must stay at least `3.14.3`.
- Pins FastAPI to `0.136.3` and Starlette to `1.3.1` in `fastapi_stats_app/requirements.txt` so the stats service stays on a Starlette release line with the current multipart and request parsing fixes.
- Pins PyJWT to `2.15.0` for FastAPI access tokens and restricts decoding to HS256 with required issuer, audience, subject, issued-at, not-before, and expiry claims.
- Removes unused `markdown` from the bot/worker requirements; Markdown rendering uses `markdown-it-py`.
- Pins `python-multipart` to `0.0.31` for multipart parser DoS fixes.
- Pins `setuptools` to `83.0.0`, `cryptography` to `50.0.0` and `weasyprint` to `70.0` in the root requirements lock for the current audit gate. The cryptography minimum is also enforced in `setup.py`; do not restore the vulnerable 46.x upper bound. Security fixes must pass the unchanged strict audit before deployment.
- Uses `scripts/build_audit_requirements.py` to build the same filtered `audit-requirements.txt` in GitHub Actions, Jenkins, and local checks. The builder excludes editable installs and the local `matplobbot-shared` package, deduplicates matching pins, and fails on conflicting pins.
- Keeps GitHub Actions and Jenkins `python -m pip_audit --strict` green with a documented ignore for `PYSEC-2024-277` only. That finding is a disputed, no-fixed-version `joblib` advisory pulled transitively by `matplobblib` via scikit-learn; this project does not load untrusted joblib pickle files.
- Runs a separate scheduled Dependency Audit workflow every day at `03:17 UTC`, so new advisories that appear after the last dependency change still fail CI.

How to use:

1. If CI reports a new dependency advisory, update the minimum safe version in `requirements.in`.
2. Refresh the lock in `requirements.txt` and update service-specific pins such as `fastapi_stats_app/requirements.txt`.
3. Run `python scripts/build_audit_requirements.py` and then `python -m pip_audit --strict -r audit-requirements.txt --ignore-vuln PYSEC-2024-277` locally before merging dependency changes.
4. Use `--ignore-vuln` only for advisories with no fixed release or a verified non-applicable code path, and document the reason next to every CI/Jenkins command that carries the ignore.
5. Keep `setup.py` aligned for editable/local installs so dev and CI environments do not drift.

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

Worker operations:

- `APP_BOT_DIR` defaults to the checkout `bot/` directory and falls back to `/app/bot` in the
  image; `APP_TEMPLATES_DIR` defaults below it. Missing required filters/config/templates abort a
  worker process at startup.
- Local and production Compose use the same bounded `celery inspect ping` healthcheck. An external
  monitor should alert on scheduler `/health` queue backlog because Docker health does not restart
  an unhealthy container by itself.

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

### Extracted Feature Services And Compatibility Facades

Source:

- `shared_lib/user_activity_repository.py`
- `shared_lib/database.py`
- `bot/services/myschedule_filters.py`
- `bot/handlers/schedule.py`
- `bot/services/settings_keyboard.py`
- `bot/handlers/settings.py`

What it does:

- Moves user profile, message-history, action-user, and export queries out of the large database module.
- Moves aggregated-schedule filter persistence, cache migration, active-subscription lookup, and built-in presets out of `ScheduleManager`.
- Moves private settings keyboard construction out of `SettingsManager`.
- Preserves the old public database functions and manager helper methods as async compatibility facades, so callers can migrate independently.

Maintenance:

1. Put new query behavior in `user_activity_repository.py`, not back into the database facade.
2. Put new My Schedule filter rules in `myschedule_filters.py`; keep allowed lesson types aligned with database normalization.
3. Put new private settings buttons in `settings_keyboard.py` and keep callback data synchronized with registered handlers.
4. Keep facade signatures until all external callers and tests have intentionally migrated.

### Stats Manual Module Mappings

Source:

- `fastapi_stats_app/routers/stats_router.py`
- `shared_lib/schemas.py`
- `main_site_frontend/stats.html`
- `main_site_frontend/js/stats.js`

What it does:

- Adds an admin-only `Modules` tab on `/stats`.
- Lists manual `discipline_name -> module_name` mappings from `discipline_modules`.
- Lets admins create, update, search, filter, and delete mappings from the website.
- Uses the same mapping table as the Telegram `/set_module Discipline | Module` command, so schedule module filters consume one shared source of truth.
- Keeps the selected tab in the URL with `/stats#modules`.
- Participates in the Stats page local i18n refresh loop, so tab labels, form controls, table actions, and loaded/saving/error statuses switch EN/RU without a reload.

How to use:

1. Sign in as an admin and open `/stats#modules`.
2. Enter the full discipline name exactly as it appears in the schedule.
3. Enter or pick a module name such as `Военная кафедра`.
4. Save the mapping, then refresh the schedule page if it already has loaded module filters.
5. Use Edit for typo fixes and Delete only when a discipline should no longer be grouped into a manual module.

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
- Docker image build/push to GHCR with CI control and Docker GitHub Actions running on Node 24. Build diagnostics remain available in action logs, while post-build summaries and `.dockerbuild` record uploads are disabled because they are not used by deployment and can stall self-hosted runners after a successful push.
- Stats visual baseline capture artifact.
- Wiki sync from `docs/wiki.md` to GitHub Wiki `Home.md`.

Jenkins + deploy features:

- `Jenkinsfile.groovy` runs a pre-deploy quality gate before touching production.
- GitHub Actions and Jenkins install the same pinned lint/test/type/coverage tools from `requirements-validation.txt`, preventing provider-specific dependency drift.
- The Jenkins quality gate creates `.jenkins-venv`, installs project and validation dependencies, checks critical FastAPI/test imports (including `yaml`), runs `ruff check . --select E9,F63,F7,F82`, and runs `python -m unittest discover -s tests -v`.
- The gate fails if unittest output shows dependency-driven skips/import errors such as missing FastAPI modules.
- `Jenkinsfile.groovy` performs production deploy and smoke checks.
- After migrations and container startup, `deploy.sh` runs
  `python -m fastapi_stats_app.bootstrap_admin` inside `mpb-fastapi-stats`. It creates
  the dedicated password administrator from `STATS_USER` / `STATS_PASS`, or
  synchronizes the password of an existing unlinked administrator. This closes the
  gap where Jenkins supplied environment credentials but `/api/auth/login` required
  a matching `web_accounts` row. Repeated provisioning preserves the ID, preferences,
  and an already matching hash. Ordinary and Telegram-linked username collisions
  fail without mutation; choose an unused `DEPLOY_ADMIN_USERNAME` parameter in Jenkins
  (default `matplobbot-deploy`). The old `PROD_STATS_USER` credential is no longer
  copied into `STATS_USER`, preventing a personal account from blocking deployment.
  The password still comes from `PROD_STATS_PASS`.
  Blank/default credentials and invalid stored hashes also fail closed. Changing
  `STATS_USER` does not remove the previous account. See
  [the provisioning module](../fastapi_stats_app/wiki_bootstrap_admin.md).
- Smoke checks read the effective API container environment with Python shell quoting,
  rather than executing `.env` as a shell script. Special characters reach the login
  request unchanged. HTTP `401` from the expected administrator remains a failure;
  successful login, authenticated HTTP/WebSocket access, and anonymous rejection
  are all mandatory. Provisioning errors stop deployment before these checks.
- Production CI traffic stays on the Proxmox LAN: the self-hosted GitHub runner calls
  `http://192.168.1.130:8080` by default, and Jenkins reaches `app-vm` through the
  `DEPLOY_HOST` build parameter, whose default is `192.168.1.40`. Before either connection,
  `scripts/resolve_private_ipv4.sh` requires exactly one RFC1918 address; `*.ts.net`, Tailscale's
  `100.64/10`, public, loopback, unresolved, and ambiguous results are rejected. GitHub's cURL
  call is pinned to the validated Jenkins IP with `--resolve` and bypasses process-wide HTTP
  proxies with `--noproxy`; Jenkins SSH uses the validated app-vm IP. Repository variables
  `JENKINS_LAN_URL` and `APP_VM_LAN_HOST` can override these defaults if the VMs receive new
  stable private addresses.
- Deploy host fingerprint pinning via `APP_VM_SHA256` (with optional one-off override).
- Jenkins streams the complete production environment into `deploy.sh --write-env`; that mode
  creates a permission-`0600` temporary file beside the target, validates every required key,
  and only then atomically renames it to `.env`. An incomplete stream leaves the prior `.env`
  untouched. Keeping temporary-variable handling inside the remote script avoids
  Groovy/Bash/SSH expansion of unset remote variables. The configured `~/matplobbot` path is
  passed to the remote shell without single-quoting the tilde so it resolves against the deploy
  user's home directory.
- `deploy.sh` pre-pulls only the GHCR application services, retries transient registry/network pull failures, and avoids unnecessary Docker Hub pulls for stable infra services on routine deploys.
- `deploy.sh` also rebuilds local build services such as `proxy` and restarts config-mounted services such as `main-site-frontend` and `caddy` so repo changes are actually applied in production.

How to use:

1. Push to `main` to run CI and image publishing.
2. Start the Jenkins deploy job; it must pass the pre-deploy quality gate before deployment starts.
3. Jenkins deploy job pre-pulls the tagged GHCR app images and runs smoke checks; routine deploys reuse already-cached `redis`, `postgres`, `nginx`, and `caddy` images instead of re-pulling them every time.
4. Confirm that `github-runner-vm`, `jenkins-vm`, and `app-vm` share a reachable Proxmox LAN.
   If the VM addresses change from the tracked defaults, set GitHub repository variables
   `JENKINS_LAN_URL=http://<jenkins-private-ip>:8080` and
   `APP_VM_LAN_HOST=<app-private-ip>`. The old `JENKINS_URL` secret is no longer used.
5. Pin the LAN-facing OpenSSH ED25519 fingerprint in the Jenkins `APP_VM_SHA256` credential.
   From `jenkins-vm`, obtain it with
   `ssh-keyscan -T 5 -t ed25519 192.168.1.40 2>/dev/null | ssh-keygen -lf - -E sha256`.
   Do not reuse a Tailscale SSH fingerprint unless it is verified to be identical, and make sure
   the public half of Jenkins credential `app-vm-ssh-key` is authorized for the deploy user in
   app-vm's regular OpenSSH server. The build parameter `DEPLOY_HOST_FINGERPRINT` remains
   available for a deliberate one-off rotation.
6. If you changed a pinned infra image tag or are deploying onto a fresh host with no cached infra images, pre-pull them once before the rollout, for example:
   `docker compose -f docker-compose.prod.yml pull redis postgres main-site-frontend caddy`
7. Keep `WIKI_PUSH_TOKEN` configured for automatic wiki mirror updates.

## Practical Notes

### Email Forwarding

- Connection format: `name@yandex.ru imap.yandex.ru 993 imap` (POP3 example:
  `name@mail.ru pop.mail.ru 995 pop3`). Explicit ports 1-65535 are saved per account.
  All connections require implicit SSL/TLS, not STARTTLS. Migration
  `f1b52c3d4e5f` backfills existing accounts with protocol-specific default ports.

- `/mail` connects up to ten mailboxes per user in private bot chats. Existing
  messages are baselined, not forwarded; subsequent INBOX arrivals are delivered.
- `/mail` is available in the bot command menu, reply keyboard, and `/help`.
- The bot reply keyboard groups command buttons two per row; Web App actions
  remain full-width for touch-friendly access.
- Supports TLS IMAP (993) and POP3 (995), approximately 30-second polling, not
  IMAP IDLE. POP3 requires stable UIDL support. Mail is never deleted or marked read.
- Providers initially allowed: Gmail, Yandex, Mail.ru and Outlook mail endpoints.
  App-password availability depends on provider/account policy; OAuth-only
  accounts are not supported. Operators may extend `MAIL_ALLOWED_HOSTS` with
  comma-separated `hostname:imap` / `hostname:pop3` entries. Only trusted hosts.
- Apply `python -m alembic upgrade head`. Generate a Fernet key with
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  and store it as `MAIL_CREDENTIAL_KEY` in the bot's secret environment. Never
  commit it. Preserve it across deployments; replacing it makes saved accounts
  and pending mail unreadable. No key means the feature is disabled.
- `MAIL_ALLOWED_HOSTS` is optional and extends the built-in trusted provider
  allow-list using `hostname:imap,hostname:pop3` entries.
- Credentials and temporary attachment/body data are Fernet-encrypted in
  PostgreSQL. No plaintext spool files are created. Each attachment is removed
  from live pending state after a successful Telegram upload; failed uploads
  remain available for retry. Backups/WAL have their own retention policy.
- Uses Telegram [Rich Messages](https://core.telegram.org/bots/api#sendrichmessage)
  with sanitized rich HTML, preserving supported emphasis, links, lists and
  tables. Rich HTML and rich Markdown target the same interface. Remote images,
  scripts and tracking pixels are not loaded. Long HTML falls back to text.
- Raw mail limit: 35 MiB; larger mail sends a notice. Body limit: 100000 characters
  with explicit truncation. Files accompany the original message as replies.
- Pause/resume and confirmed removal are available per mailbox. Removal does
  not change the provider mailbox or retract previously sent Telegram content.
  Revoke the provider app password separately when disconnecting permanently.
- Delivery progress is transactional, but the Telegram API has no idempotency
  key: ambiguous network failures can duplicate a sent component. Initial
  acceptance testing requires an explicitly supplied test mailbox and chat.

- Public calendar links are secrets. Rotate immediately if exposed.
- `Caddyfile` contains only public application/API routes. Personal or
  private-network proxies belong in the ignored deployment-local
  `Caddyfile.local`, mounted into the Caddy container and imported by the
  public file. Compose defaults to the safe tracked
  `Caddyfile.local.example`; production hosts set
  `CADDY_LOCAL_FILE=./Caddyfile.local` before starting Compose. Provision that
  file on every host and do not commit internal IP addresses.
- Legacy stats alias `/api/stats/stats/action_users` is deprecating; migrate clients to `/api/stats/action_users`.
- Website API base can be switched per environment with `window.__MPB_API_BASE__`.
- Bot and website schedule features are intentionally coupled through shared subscription data and cached schedule sources.

## Security Maintenance Notes

- Avatar responses use `/api/stats/users/{user_id}/avatar`; the backend keeps the Telegram bot token server-side and only proxies users already present in the application database. The proxy uses the shared Telegram HTTP/proxy configuration and a bounded in-memory cache.
- Production FastAPI deployments must set `ENVIRONMENT=production` (the production Compose file sets it explicitly) and provide a non-default `STATS_PASS` and a random `JWT_SECRET_KEY` of at least 32 bytes. Development may use an ephemeral JWT key, which invalidates tokens after restart.
- Keep `JWT_ISSUER` and `JWT_AUDIENCE` stable across replicas. Changing either value invalidates existing sessions by design.
- LaTeX compilation rejects shell execution, direct file I/O, unsafe external file references, absolute paths, and traversal. Compilation runs from the temporary project directory with `-no-shell-escape` and a non-root worker.
- Long Telegram HTML messages are split into balanced chunks. Callers must provide a positive `max_chars` large enough for the tags they need to preserve.
- Keep TatSu pinned below `5.7`: `ics==0.7.2` still uses the `buffer_class` parser option removed by later TatSu releases. Verify `from fastapi_stats_app.main import app` after dependency updates.
- Studio upload and rename endpoints accept one safe filename component only;
  path separators, control characters, absolute paths and traversal attempts are rejected.
- Daily catch-up reads active Telegram profiles and computes their latest local
  scheduled occurrence from the native PostgreSQL `TIME` value and timezone.
  Exact-time notification lookups remain available for compatibility.
  `REDIS_URL` is authoritative for the shared client,
  Celery, and bot FSM; `REDIS_HOST`, `REDIS_PORT`, and `REDIS_DB` are the compatibility fallback.
- Generated Telegram inline-button hashes use the bounded local
  `CallbackPathCache` first and Redis keys named `callback_path:<hash>` as a
  restart/replica-safe fallback. `CALLBACK_PATH_TTL_SECONDS` controls the
  persistence window (14 days by default). A Redis outage keeps local buttons
  usable; the admin `/clear_cache` operation removes both local and persistent
  callback mappings.
- Cached schedule rows store their display label in `entity_name`; the offline
  list no longer expands every semester JSON document at request time.
- Schedule snapshots keep only the three most recent entities and tolerate
  unavailable or quota-limited browser storage. Telegram Mini App BackButton is
  shown only when browser history has a previous entry.


## UI/UX: выбранные улучшения от 9 октября 2026

Реализованы пункты 1–15 и 17–35 согласованного UI/UX-аудита. Пункт 16
(резервный сценарий при недоступном Telegram Widget) исключён по просьбе пользователя.
Вход в аккаунт остаётся через плашку Telegram-профиля в общей навигации.

| Пункты | Поведение |
| --- | --- |
| 1–2 | Компактная навигация до 1280 px; общие цвета, поверхности, фокус, кнопки и RU/EN/тёмная тема. |
| 3–4 | Прямые действия и последние открытые объекты на главной; `/project` загружает настоящий README Ackrome/matplobbot через GitHub API с оглавлением, кодом, ссылками, санитизацией и сохранённой копией. |
| 5–10 | Компактный первый экран расписания; «Сегодня» открывает и фокусирует день; поиск Arrow/Enter/Escape; компактная таблица и полные сведения о занятии; подсказка пустого поиска; спокойный статус свежих данных, заметные предупреждения при сбое. |
| 11–12 | Сохраняемое сравнение выбранных сущностей с модулями/режимом занятий, inline-валидацией дат и времени, шкалой занятий и общих свободных окон. Неизвестные данные не считаются свободным временем. |
| 13, 34 | Основное действие календаря зависит от выбранного приложения; разовый ICS явно обозначен. Модальное окно календаря удерживает фокус и возвращает его к кнопке открытия. |
| 14–15, 19 | Аккаунт объединяет инструменты, тему, язык и переходы к настройкам/данным Telegram. Выгрузка ZIP содержит account.json, описание и исходные файлы по исходным относительным путям; JSON доступен отдельно. Удаление вынесено в раскрываемую опасную зону с прежними проверками свежей выгрузки. |
| 17–18 | Контекстный заголовок входа; пароль администратора раскрывается отдельно; поля имеют labels/autocomplete и переключатель видимости. |
| 20–24 | Атомарное сохранение черновика как проекта; помощь до первой сборки; поиск/переименование/копия/удаление проектов; схемы шаблонов; отдельные сохранение Ctrl/Cmd+S и сборка Ctrl/Cmd+Enter; увеличенные цели действий. |
| 25–26 | Ошибка сборки открывает файл/строку. Конфликт локальной и серверной версии показывает обе версии, отличия и скачивание обеих до выбора. Это восстановление черновика, не серверная история версий. |
| 27–29 | Локальная история 20 сборок с датой/состоянием/отпечатком и получением результата в течение 24 часов; реальная кооперативная отмена компилятора; очередь файлов с частичным успехом и повтором в исходный проект; названия скачиваний связаны со снимком сборки. |
| 30–32 | Админка разделена на состояние сервиса, использование и модули; действия зависят от контекста; при недоступном Chart.js данные остаются таблицей с повторной загрузкой графика. |
| 33 | Локализованная офлайн-страница предлагает повтор и только действительно кэшированные оболочки. |
| 35 | Авторизованные измерения времени до расписания, результата сборки, получения ссылки календаря и восстановления после ошибки. Без текстов документов/поиска; агрегаты доступны администратору, хранение 90 дней с удалением данных аккаунта. |

### Контракты и ограничения

- `PATCH /api/studio/projects/{id}`, `POST /api/studio/projects/{id}/duplicate` и
  `DELETE /api/studio/projects/{id}` проверяют владельца. Создание принимает
  `initial_content` и сохраняет проект с главным файлом одной транзакцией.
- `POST /api/studio/jobs/{id}/cancel` записывает ограниченный по TTL маркер;
  `cancelling` не означает завершение. Worker останавливает собственную группу
  процессов компилятора и только затем возвращает `cancelled`. Завершённый результат
  выигрывает гонку с поздней отменой. Поведение основано на
  [ограничениях Celery revoke](https://docs.celeryq.dev/en/stable/userguide/workers.html#revoke-revoking-tasks).
- Для измерений нужна миграция `f8e9f0a1b2c3`. Время подключения календаря означает
  получение ссылки/запуск внешнего приложения; подтверждение импорта во внешнем
  календаре сайту недоступно. Метрики best effort и не являются SLA.
- API расписания возвращает исходные нормализованные интервалы `lessons` для
  визуализации. Прежние ограничения: до шести сущностей, до 14 дней, текущий семестр.
- Офлайн-кэш `mpb-site-v41` включает новые оболочки, скрипты и общие стили.
  Текст публичного README кэшируется отдельно на устройстве. Доступность библиотеки
  рендеринга и внешних изображений зависит от сети; предусмотрены понятные состояния.

### Проверка

UI проверяется локальным Chromium на синтетических API-данных при ширинах 390, 820 и
1440 px, с RU/EN и тёмной темой. Скриншоты оцениваются после действий, включая
неуспешную сборку, частичную загрузку, конфликт версий и блокировку CDN. README взят
из публичного GitHub; Marked/DOMPurify используются реальные закреплённые версии.
Скриншоты и временные сценарии не включаются в репозиторий.

Backend-регрессии покрывают владельцев проектов/сборок, атомарный импорт черновика,
копирование бинарных исходников, отмену до запуска/во время процесса, ограничение
содержимого измерений и реальные SQL-агрегаты. ZIP читается стандартным zipfile с
проверкой CRC/Unicode/бинарных данных. Общий gate — `coverage run --branch -m unittest
discover -s tests -v`, ruff, JS syntax, сборка Tailwind, совпадение asset URL и precache.
Эти проверки не означают развёртывания или реальной отправки документов в Telegram.

Итог локального прогона: 381 тест прошёл, покрытие с учётом ветвлений — 58%; 14 браузерных
сценариев и пять дополнительных проверок прошли без JavaScript-ошибок. Отдельно
проверены реальные Monaco и Markdown/KaTeX, загрузка README с изображениями,
копирование готовой календарной ссылки и восстановление Chart.js после сбоя CDN.
После визуальной проверки добавлена подсказка горизонтальной прокрутки шкалы
сравнения. Скриншоты покрывают все 34 включённых пункта; Telegram-переходы
проверены по deep links и тестам обработчиков, без отправки в реальный чат.

### Подробная карточка занятия (9 октября 2026)

Нажатие на карточку в таблице или списке открывает отдельное окно с сильным
размытием фона, без изменения ширины расписания. Заголовок остаётся кнопкой для
клавиатуры; вложенные действия копирования и меню работают самостоятельно.

- **Занятие:** полное название и тип, дата, интервал и длительность в МСК,
  аудитория/корпус, имя и почта преподавателя, группа, подгруппа, модуль,
  примечания и ссылки — при наличии в исходных данных. Числовой ID преподавателя
  не выводится вместо имени. Источник, время проверки и состояние сохранённой
  копии находятся в раскрываемом блоке.
- **Дисциплина:** хронологический список и количество занятий по типам во всём
  загруженном расписании текущей сущности, включая недели вне текущего экрана.
  Диапазон указан явно: список не заявляется полным учебным планом. Точные дубли
  исключаются, разные группы, подгруппы, аудитории и преподаватели сохраняются.
  Нажатие на запись открывает сведения именно об этой паре.
- **Действия:** копирование сведений с ручным запасным вариантом; в «Ещё действия»
  — скачивание одного занятия в ICS и переходы к расписаниям преподавателя,
  аудитории и группы. Известный ID сущности имеет приоритет над поиском по имени.
  Невалидные даты/интервалы не экспортируются.
- **Доступность:** нативная модальность, Tab/Shift+Tab внутри окна, стрелки между
  вкладками, Escape/backdrop/кнопка закрытия; восстановление фокуса и прокрутки.
  До 600 px окно занимает экран; поддержаны RU/EN и обе темы.

Реализация: `main_site_frontend/js/lesson_details.js` и
`main_site_frontend/css/lesson_details.css`, интеграция — `schedule.js`.
Новых серверных маршрутов или хранилищ нет. Описания курса, правила оценивания
и материалы без отдельного достоверного источника не добавляются.
Контракты данных, URL и времени проверяет `tests/test_lesson_details.py`;
интерфейс проверяется локальным браузером со снимками экрана и API-фикстурами.

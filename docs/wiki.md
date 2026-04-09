# Bot Feature Wiki

This document covers the user-facing bot, scheduler, and website features currently described here:

- unified global search via `/search`
- saved search presets via `/search_presets`
- schedule table lecturer-name toggle on the website
- website iCal subscription links for authorized users
- scheduler proxy support via `PROXY_URL`

## Quick Index

### Search Features

| Feature | Entry point | Purpose |
| --- | --- | --- |
| Unified global search | `/search` | Search library content and linked GitHub notes from one screen |
| Search presets | `/search_presets` | Save and rerun commonly used searches |

### Scheduler Feature

| Feature | Entry point | Purpose |
| --- | --- | --- |
| Scheduler proxy support | `PROXY_URL` env var | Route scheduler Telegram delivery through a proxy |

### Website Schedule Features

| Feature | Entry point | Purpose |
| --- | --- | --- |
| Unified schedule search | Website schedule page search bar | Find groups, lecturers, and auditoriums from one search field |
| Full lecturer name toggle | Website schedule page filters | Show the full lecturer name in desktop table cards |
| iCal subscription links | Website schedule page for authorized users | Copy or rotate a personal calendar subscription link |
| Configurable frontend API base | `window.__MPB_API_BASE__` or `<meta name="mpb-api-base">` | Use relative `/api` by default or override frontend API host per environment |
| Styled popup notifications | `window.mpbPopup(message, options)` | Replace browser alerts with unified dismissible popup notifications |

## Website Schedule Search

### Purpose

The website schedule search bar supports mixed search across:

- groups
- lecturers
- auditoriums

Users no longer need a separate search mode for each schedule entity type.

### User Flow

1. Open the website schedule page.
2. Type at least two characters into the search bar.
3. The dropdown returns matching groups, lecturers, and auditoriums together.
4. Each result shows its entity type badge.
5. Clicking any result loads the matching schedule in the same page.

## Unified Global Search

### Purpose

`/search` gives the user one search entry point that can search across:

- the internal `matplobblib` library
- Markdown notes from the user's linked GitHub repositories

The goal is to let the user search both sources at once and open results in the correct viewer without switching commands manually.

### Entry Points

Users can open unified search from:

- the `/search` command
- the bot command menu
- the `/help` menu button for unified search

### User Flow

1. The user sends `/search`.
2. The bot opens the global search panel and creates a fresh per-user search context in Redis.
3. The panel shows enabled sources and available GitHub repository filters.
4. The user sends a plain-text query.
5. The bot runs the search and edits the status message into a paginated results list.
6. The user can open a result, change enabled sources, limit GitHub search to selected repositories, or save the current search as a preset.

### Search Sources

#### Library source

The library side uses the semantic search engine with:

```text
source_type="lib"
```

Each result contains:

- `kind = "library"`
- `path`
- `score`

Opening a library result routes to the normal library display flow.

#### GitHub source

The GitHub side searches only repositories already linked in the current user's bot settings.

For each linked repository, the semantic search engine is called with:

```text
source_type=f"repo:{repo_path}"
```

Each result contains:

- `kind = "github"`
- `repo_path`
- `path`
- `score`

Opening a GitHub result routes to the GitHub Markdown viewer flow.

### Filters

The unified search UI supports two filter levels.

#### Source filters

The user can enable or disable:

- Library
- GitHub

Rules:

- At least one source must remain enabled.
- If the user tries to disable the last enabled source, the bot shows an alert and does not apply the change.

#### Repository filters

If GitHub is enabled and the user has linked repositories, the panel shows one toggle per linked repository.

Rules:

- repository filters affect GitHub results only
- the user can search any subset of linked repositories
- if GitHub is enabled and no explicit subset exists yet, all linked repositories are selected by default
- if GitHub is disabled, the active repository list is cleared from the normalized filter state

### Default State

When `/search` is opened:

- Library is enabled by default.
- GitHub is enabled by default if the user has at least one linked repository.
- All linked repositories are selected by default.
- The initial panel is shown before any query is run.

### Search Execution

Before each search, the bot normalizes filters so outdated or invalid repository selections are removed automatically.

If both sources are enabled, the bot searches them in parallel:

- library search: up to 20 results
- GitHub search: fetched per selected repository, then merged

The merged result list is:

1. sorted by semantic score descending
2. sorted library-first on equal score
3. capped at 20 items

GitHub results are deduplicated by Markdown file path within each repository before merging.

### Pagination And Presentation

Global results use the standard bot pagination pattern:

- `SEARCH_RESULTS_PER_PAGE = 10`
- page navigation is inline
- pagination does not rerun the search; it only changes the current page view

Result presentation rules:

- library results are shown as library items
- GitHub results include the repository name and file path
- library results open in the library viewer
- GitHub results open in the GitHub Markdown viewer

### Re-running On Filter Changes

If the user already has a query in the current `/search` session and then changes:

- enabled sources
- selected repositories

the bot immediately reruns the last query with the updated filters and refreshes the results list.

If no query has been entered yet, the bot only refreshes the panel text and buttons.

### Cache And Session Scope

The active unified search session is stored in Redis under:

```text
global_search
```

The stored payload contains:

- `query`
- `filters`
- `results`

This cache is used for:

- pagination
- source toggles
- repository toggles
- `Save preset`
- reopening result items by index

### Limitations

- GitHub unified search only works for repositories linked in the user's bot settings.
- Unified search does not search arbitrary GitHub repositories.
- Unified search currently covers library content and linked GitHub Markdown content only. It does not include schedule entities.
- If the cached search context is missing, actions such as pagination or preset saving fail gracefully with an outdated or missing context message.

## Search Presets

### Purpose

Saved presets let users store a reusable search configuration and reopen it later without retyping the query or rebuilding filters manually.

This feature works for:

- library search
- GitHub Markdown search
- schedule entity search
- unified global search

### Entry Points

Users can open presets from:

- the `/search_presets` command
- the bot command menu
- the `/help` menu button for search presets

Users can create presets from supported results screens with the `Save preset` button.

The button is available on:

- `/matp_search` results
- `/lec_search` results
- `/schedule` search results
- `/search` unified search results

The button appears only after a valid search result context has been created and cached.

### Supported Preset Types

Each preset stores a `search_kind` so the bot knows how to reopen it.

| Preset type | `search_kind` | Saved data | Reopen behavior |
| --- | --- | --- | --- |
| Library | `library` | query, empty filters | reruns library semantic search |
| GitHub | `github` | query, selected `repo_paths` | reruns Markdown search in the same linked repo |
| Schedule | `schedule` | query, `search_type` | reruns schedule entity search in the same mode |
| Global | `global` | query, source state, selected repositories | reruns unified search with the same source and repo filters |

Current schedule modes are the existing bot modes such as:

- group
- person
- auditorium

Important note:

- a schedule preset stores the search mode, not a chosen result item

### Saving A Preset

1. The user performs a supported search and reaches a results screen.
2. The user taps `Save preset`.
3. The bot reads the latest search context from Redis.
4. The bot asks the user to send a preset name.
5. The user sends a name.
6. The preset is stored in user settings and the bot immediately shows the presets list.

Important behavior:

- the preset is based on the latest cached search for that scope
- search results themselves are not stored in the preset
- if the cache is missing or outdated, the bot refuses the save action

Validation rules:

- the preset name is trimmed
- empty names are rejected
- the name is limited to 60 characters
- a preset cannot be saved without a valid cached search context

### Reopening A Preset

1. The user sends `/search_presets`.
2. The bot shows all saved presets in a single inline list.
3. Each row shows a run button with a short scope label and a delete button.
4. The user taps the run button.
5. The bot loads the preset and dispatches it to the matching search flow.

Scope labels:

- `LIB` for library presets
- `GH` for GitHub presets
- `SCH` for schedule presets
- `ALL` for unified global presets

### Reopen Behavior By Type

#### Library preset

The bot reruns library semantic search and rebuilds the normal `lib_search` cache used by the library results UI.

#### GitHub preset

The bot checks whether the saved repository is still linked for the user.

If the repository still exists:

- Markdown search is rerun for that repository
- the normal `md_search` cache is rebuilt

If the repository was removed:

- the bot warns the user that the repository is no longer linked
- the preset remains stored until the user deletes it

#### Schedule preset

The bot reruns schedule search with the saved:

- query
- search type

This rebuilds the `schedule_search` cache used by the schedule results flow.

#### Global preset

The bot reruns unified search with the saved:

- query
- source toggles
- repository subset

The `global_search` cache is recreated so pagination and result opening work the same way as a fresh `/search` run.

### Deleting Presets

Users delete presets directly from the `/search_presets` list by tapping the delete button on a row.

Behavior:

- deletion removes the preset from persistent user settings
- the preset list message is refreshed in place
- if the preset no longer exists, the bot shows a safe not-found or outdated response

### Storage And Limits

Presets are stored in persistent per-user settings, not in Redis.

Storage location:

```text
User.settings["search_presets"]
```

Each preset record contains:

- `id`
- `name`
- `search_kind`
- `query`
- `filters`
- `created_at`
- `updated_at`

Preset rules:

- presets are sorted by `updated_at`, falling back to `created_at`
- newest or most recently updated presets appear first
- the maximum stored preset count per user is `15`

If a future update path reuses an existing preset id, the preset is replaced and moved according to its new update timestamp.

### Cache Dependency

Creating a preset depends on the latest search cache still being available.

The save flow reads one of these per-user Redis keys:

- `lib_search`
- `md_search`
- `schedule_search`
- `global_search`

If the expected cache is missing or does not contain a valid query, the bot refuses to create the preset and tells the user there is no recent search to save.

### Operational Notes

- Presets are personal and are not shared between users.
- Presets are language-neutral in storage.
- Presets do not snapshot search results; they only snapshot the query and filters.
- Reopening a preset always runs a fresh search.
- A GitHub preset becomes non-runnable if its repository is no longer linked, but it remains visible until deleted.

## Website Schedule Features

### Full Lecturer Name Toggle

#### Purpose

The website schedule page now includes a separate filter for lecturer display in the desktop table view.

With this toggle enabled:

- desktop lesson cards show the full lecturer name
- copy-to-clipboard still copies the full lecturer name
- mobile cards stay unchanged and continue to show the full lecturer name as before

#### How To Use It

1. Open the website schedule page.
2. Load any group, lecturer, or auditorium schedule.
3. Open the filters panel.
4. Toggle `Full lecturer name`.

The preference is stored in the same website schedule preferences payload as the existing module and short-name options, so it persists for signed-in users and in local browser storage.

### Configurable Frontend API Base

#### Purpose

Website frontend modules now resolve API endpoints from one shared base instead of hardcoded host strings.

This allows:

- same-origin production deployments through relative `/api`
- staging/testing environments to override API host without editing multiple JS files
- consistent API routing across `navbar`, `auth`, `schedule`, `stats`, and `studio` scripts

#### How To Use It

1. Shared static frontend setup:
   - `main_site_frontend/js/runtime_config.js` now sets:
   - `window.__MPB_API_BASE__ = "https://api.ivantishchenko.ru/api";`
2. Default behavior without any override:
   - frontend uses `/api`
3. To override globally, set `window.__MPB_API_BASE__` before page scripts:

```html
<script>
  window.__MPB_API_BASE__ = "https://example.com/api";
</script>
```

4. Or set a page-level meta override:

```html
<meta name="mpb-api-base" content="https://example.com/api" />
```

5. Resolution order:
   - `window.__MPB_API_BASE__`
   - `<meta name="mpb-api-base">`
   - fallback `/api`

### Styled Popup Notifications

#### Purpose

Frontend alert dialogs were replaced with a shared popup notification helper for better UX.

#### How To Use It

1. Call:

```js
window.mpbPopup("Saved successfully", { type: "success" });
```

2. Supported `type` values:
   - `info`
   - `success`
   - `warning`
   - `error`
3. Optional options:
   - `title`: custom popup header
   - `duration`: auto-close timeout in milliseconds (default about 4.2 seconds)
4. The helper auto-injects styles/container and renders stacked, dismissible popups in the top-right corner.

### Schedule/Auth Text Fixes (P3 Front)

#### What Changed

- Replaced remaining hardcoded schedule toggle label fallback to localized `Полное имя преподавателя`.
- Removed visible mojibake symbols in frontend UI controls that were showing broken characters.
- Updated auth page/script messages to keep runtime text localized and consistent with UI language.

### Website iCal Subscription Links

#### Purpose

Authorized website users can now open the schedule page and manage their personal calendar subscription link directly from the site.

The website now manages a richer iCal sync model on its own side:

- multiple private feed profiles per user
- built-in feeds for `All classes` and `Exams only`
- custom feeds saved from the current website schedule page
- masked private URLs by default with reveal/copy controls
- Apple, Google, and Outlook specific subscribe instructions
- test and download actions for the raw `.ics` feed
- feed health metadata such as event count, next event, cache status, source update time, and last external access

#### How To Use It

1. Sign in on the website.
2. Open the schedule page.
3. Find the collapsible `Calendar subscription` section above the main schedule block.
4. Expand the section to review eligibility, active subscription counts, feed health, and the currently selected sync profile.
5. Choose a profile:
   - `All classes`
   - `Exams only`
   - or a saved preset created from the current website schedule page
6. Use `Copy link` for Google Calendar or other HTTPS ICS clients.
7. Use `Reveal link` only when you need to inspect the full private URL directly.
8. Use `Open on iOS / Mac` for Apple Calendar compatible devices.
9. Use `Test feed` to open the raw `.ics` URL in a new tab.
10. Use `Download .ics` to fetch the feed once.
11. Use `Save current view` to create a separate website-owned feed for the currently opened schedule page and its selected modules.
12. Use `Disable sync` to stop all website calendar feeds temporarily without rotating the secret.
13. Use `Reset link` to revoke the old private URL and issue a new one immediately.

#### Availability Rules

- the card is shown only for authorized website users
- the subscription becomes active only for accounts linked to Telegram schedule subscriptions
- if the account is authorized but not linked to Telegram schedule data, the website shows an unavailable state instead of a link
- website iCal settings are stored in website account preferences and do not reuse Telegram quick filters from Redis
- the expanded panel explains the source, scope, time window, access model, and current feed health of each sync profile
- disabling sync makes the public feed URLs stop serving updates until sync is enabled again

#### Backend Endpoints

The website uses these authenticated API endpoints:

- `GET /api/cal/subscription`
- `POST /api/cal/subscription/reset`
- `POST /api/cal/subscription/toggle`
- `POST /api/cal/subscription/select`
- `POST /api/cal/subscription/profiles`
- `DELETE /api/cal/subscription/profiles/{profile_id}`

Public feed URLs remain available through the existing secret link and now also support profile-specific routes:

- `GET /api/cal/{secret}.ics`
- `GET /api/cal/{secret}/profiles/{profile_id}.ics`

Both public feed routes support `?download=1` and now return `ETag` / `Last-Modified` headers for calendar clients.

### Schedule Last Parsed Time

#### Purpose

Both bot and website schedule views now show when the source schedule was last parsed and cached from the university API.

#### Where It Appears

- Bot `/schedule` responses:
  - day view from search result
  - day view from calendar
  - week view
  - `/myschedule` per-subscription daily updates
- Website schedule page:
  - context bar line now includes the loaded range and source parsed timestamp

#### Data Source

- Backend reads `cached_schedules.updated_at` for the selected entity.
- API endpoint `GET /api/schedule/data/{type}/{id}` now includes:

```json
{
  "source_updated_at": "2026-04-06T10:30:00+00:00"
}
```

#### Notes

- If no cached timestamp exists yet, the UI falls back to a localized "unknown parsed time" message.
- Bot display is formatted in Moscow time.

### Bot Calendar Link: Telegram-Filtered Feed

#### Purpose

When users open the calendar link from the bot, the generated feed should respect Telegram subscription/module filtering choices.

#### Behavior

- The bot now sends a link to:

```text
/api/cal/{secret}/telegram.ics
```

- This feed is generated from active Telegram schedule subscriptions and applies Telegram-side filters, including selected modules where configured.

#### Public Endpoints

- `GET /api/cal/{secret}/telegram.ics`
- `GET /api/cal/{secret}/telegram/basic.ics`

Both support `HEAD` and optional `?download=1`.

### User Stats Export Formats

#### Purpose

Admin user detail export now supports multiple formats from one endpoint.

#### Endpoint

`GET /api/stats/users/{user_id}/export_actions`

#### Query Parameters

- `format=json|csv|weekly_pdf` (default `json`)
- `download=1` (used for downloadable JSON file mode)

#### Examples

- JSON payload (API response):

```text
/api/stats/users/123/export_actions
```

- Download JSON file:

```text
/api/stats/users/123/export_actions?format=json&download=1
```

- Download CSV file:

```text
/api/stats/users/123/export_actions?format=csv
```

- Download weekly PDF report:

```text
/api/stats/users/123/export_actions?format=weekly_pdf
```

#### UI

The user detail dashboard page now has separate export actions for CSV, JSON, and weekly PDF.

### Stats Action Users Endpoint

#### Purpose

The admin dashboard "users by action" drill-down now uses a canonical API route that matches frontend requests.

#### Endpoint

Canonical route:

```text
GET /api/stats/action_users
```

Backward-compatible legacy alias (still supported):

```text
GET /api/stats/stats/action_users
```

#### Query Parameters

- `action_type` (required)
- `action_details` (required)
- `page` (optional, default `1`)
- `page_size` (optional, default `15`)
- `sort_by` (optional, default `full_name`)
- `sort_order` (optional, default `asc`)

### Stats Sort Allowlists

#### Purpose

Stats profile and action-users APIs now use explicit allowlists for sorting params.

#### Allowed Values

`GET /api/stats/users/{user_id}/profile`

- `sort_by`: `id`, `action_type`, `action_details`, `timestamp`
- `sort_order`: `asc`, `desc`

`GET /api/stats/action_users`

- `sort_by`: `user_id`, `full_name`, `username`
- `sort_order`: `asc`, `desc`

Invalid values are now rejected with `422` instead of silently falling back.

### Admin Message Rate Limit And Audit Metadata

#### Purpose

`POST /api/stats/users/{user_id}/send_message` now has abuse protection and structured audit logs.

#### Behavior

- per-admin rate limit is enforced (default: `12` requests per `60` seconds)
- limit can be changed with env var:

```text
ADMIN_SEND_MESSAGE_RATE_LIMIT
```

- each request writes an audit log entry with:
  - `admin_id`
  - `target_id`
  - `timestamp`
  - `result` (`success`, `rate_limited`, `telegram_error`, `network_error`, etc.)
  - `correlation_id`

#### Response

Successful responses now include:

```json
{
  "status": "success",
  "correlation_id": "..."
}
```

### Correlation ID In API/Scheduler Logs

#### Purpose

FastAPI and scheduler logs now include correlation ids for incident tracing.

#### FastAPI Usage

- middleware sets request id from `X-Request-ID` if provided
- otherwise generates one automatically
- response returns `X-Request-ID` header
- log format includes `[cid=...]`

#### Scheduler/Admin Propagation

- scheduler jobs now generate operation correlation ids and include them in job logs
- admin send-message audit logs include the same correlation id

### Schedule Fallback Counters

#### Purpose

Track upstream schedule source health over time.

#### Counters

The shared schedule fetch path now increments Redis-backed counters:

- `ruz_api_success`
- `cache_fallback`
- `no_cache`

#### Endpoint

Admin-only endpoint to read counters:

```text
GET /api/schedule/fallback_counters
```

### Localization Completeness And Fallback

#### What Was Added

- New RU/EN keys for updated bot schedule flows and error/status messages.
- Key-parity safety test for locale files.
- Translator fallback behavior test (missing key in selected locale falls back to default locale, then to `_key_` marker).

#### Tests

- `tests/test_localization_completeness.py`

## Scheduler Proxy Support

### Purpose

The scheduler service can use `PROXY_URL` for Telegram message delivery.

RUZ schedule API requests continue to use a direct session.

### How To Enable It

1. Set `PROXY_URL` in `.env`, for example:

```text
socks5://proxy:20170
```

2. Restart `mpb-scheduler`.
3. Check the scheduler logs for:

```text
Using proxy for scheduler Telegram session
```

That log line confirms the proxy-aware Telegram session was applied.

### Failure Behavior

If a scheduler delivery window is reached and every attempted send fails:

- the job now raises an error
- the failure is visible in logs
- the run no longer appears successful only because APScheduler itself stayed alive

## Jenkins Deploy Host Fingerprint

Jenkins deploy SSH now verifies the deploy host against a pinned SHA256 host fingerprint before opening an SSH session.

### Setup

1. In Jenkins, create a Secret Text credential with id `APP_VM_SHA256`.
2. Put the deploy host ED25519 fingerprint there in the form `SHA256:...`.
3. The pipeline reads that credential by default for deploy, smoke-check, and deploy-host fallback notification SSH access.

### Optional Override

- The build parameter `DEPLOY_HOST_FINGERPRINT` can still be used as a one-off override.
- If both the override and `APP_VM_SHA256` are empty, the pipeline now fails instead of falling back to TOFU host trust.

## P2 API And Dashboard Updates (2026-04-09)

### User Action Export Date Range And Timezone

#### Purpose

`GET /api/stats/users/{user_id}/export_actions` now supports date-range filtering with explicit timezone handling for JSON, CSV, and PDF exports.

#### Query Parameters

- `date_from` (optional, `YYYY-MM-DD`, inclusive)
- `date_to` (optional, `YYYY-MM-DD`, inclusive)
- `timezone` (optional, IANA timezone, default `UTC`)

#### How To Use It

1. Open user details page (`/users/{user_id}`) in the stats UI.
2. Set `From`, `To`, and `Timezone` in the export toolbar (desktop).
3. Click CSV / JSON / PDF export buttons.
4. Use `Clear` to remove date filters and export full history again.

Direct API examples:

```text
/api/stats/users/123/export_actions?format=csv&date_from=2026-04-01&date_to=2026-04-07&timezone=Europe/Moscow
```

```text
/api/stats/users/123/export_actions?format=weekly_pdf&date_from=2026-03-01&date_to=2026-03-31&timezone=UTC
```

Validation behavior:

- invalid timezone returns `400`
- `date_from > date_to` returns `400`
- malformed date format returns `422`

### Dashboard Partial Degradation State

#### Purpose

The website stats dashboard now distinguishes between:

- full outage (all widget loads fail)
- partial degradation (for example, leaderboard fails but activity loads)

#### How It Works

- REST refresh now loads leaderboard and activity independently.
- If only one widget fails, the dashboard keeps rendering healthy widgets and shows a yellow partial-degradation banner.
- Widget-level status labels show whether stale/last-known data is being displayed.
- Connection badge changes to `Partial degradation` instead of hard offline for partial failures.

#### How To Use It

1. Open website stats dashboard.
2. If one API block fails, look for the yellow degradation banner and per-widget status text.
3. Use `Retry` to reload both widgets, or hide the banner with `Hide`.

### OpenAPI Alias Examples For Schedule Search Type

#### Purpose

`GET /api/schedule/search` now documents explicit `type` aliases so clients do not guess mappings.

#### Alias Mapping

- `lecturer` -> `person`
- `teacher` -> `person`
- `room` -> `auditorium`

#### How To Use It

1. Open API docs.
2. Inspect `GET /api/schedule/search` query parameter `type`.
3. Use documented aliases directly in frontend/client requests when needed.

Example:

```text
/api/schedule/search?term=ivan&type=lecturer
```

### Schedule Data base_date Validation

#### Purpose

`GET /api/schedule/data/{type}/{id}` now validates `base_date` through FastAPI date parsing to prevent accidental `500` responses.

#### How To Use It

- Send `base_date` only in `YYYY-MM-DD` format.
- Invalid values now return validation response `422` with field-level error details.

Example:

```text
/api/schedule/data/group/12345?base_date=2026-04-09
```

### Legacy Action Users Alias Deprecation Plan

#### Purpose

Legacy route `/api/stats/stats/action_users` now has an explicit deprecation/migration path.

#### Current Behavior

- Canonical route: `/api/stats/action_users`
- Legacy alias still works (when enabled) but now returns deprecation headers:
  - `Deprecation: true`
  - `Sunset: Tue, 01 Jul 2026 00:00:00 GMT` (planned removal window)
  - `Warning` with migration message

#### Removal Control

- Environment flag `ENABLE_LEGACY_ACTION_USERS_ALIAS=false` disables the legacy alias immediately.
- Disabled alias returns `410 Gone` with canonical-route guidance.

#### Migration Instruction

Move all clients to:

```text
/api/stats/action_users
```

## Maintainer Summary

- `/search` adds a single search surface for library and linked GitHub Markdown content.
- `/search_presets` adds persistent saved searches for library, GitHub, schedule, and global search.
- website schedule search now returns groups, lecturers, and auditoriums from one search field
- website schedule now supports a persistent `Full lecturer name` toggle for desktop table cards
- authorized website users can manage profile-based iCal sync feeds from the schedule page, including current-page presets, masked links, platform guidance, and feed health metadata
- user action export API now supports `date_from` / `date_to` / `timezone` filtering with UI controls on user details page
- stats dashboard now exposes explicit partial-degradation UI state when only some widgets fail
- schedule API docs now explicitly document `type` aliases (`lecturer`, `teacher`, `room`)
- schedule data `base_date` now returns validation `422` on invalid format
- legacy `/api/stats/stats/action_users` now emits deprecation headers and supports controlled shutdown via env flag
- active search sessions live in Redis
- saved presets live in `User.settings`
- Jenkins deploy SSH uses pinned host fingerprint verification from `APP_VM_SHA256` by default
- scheduler Telegram delivery can use `PROXY_URL`

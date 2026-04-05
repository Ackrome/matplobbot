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
| Full lecturer name toggle | Website schedule page filters | Show the full lecturer name in desktop table cards |
| iCal subscription links | Website schedule page for authorized users | Copy or rotate a personal calendar subscription link |

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

### Website iCal Subscription Links

#### Purpose

Authorized website users can now open the schedule page and manage their personal calendar subscription link directly from the site.

The website reuses the same private calendar feed format as the bot:

- HTTPS link for copy/paste into calendar clients such as Google Calendar
- `webcal://` link for Apple Calendar style subscription flows

#### How To Use It

1. Sign in on the website.
2. Open the schedule page.
3. Find the `Calendar subscription` card above the main schedule block.
4. Use `Copy link` for Google Calendar or other ICS clients.
5. Use `Open on iOS / Mac` for Apple Calendar compatible devices.
6. Use `Reset link` to revoke the old URL and issue a new one.

#### Availability Rules

- the card is shown only for authorized website users
- the subscription becomes active only for accounts linked to Telegram schedule subscriptions
- if the account is authorized but not linked to Telegram schedule data, the website shows an unavailable state instead of a link

#### Backend Endpoints

The website uses these authenticated API endpoints:

- `GET /api/cal/subscription`
- `POST /api/cal/subscription/reset`

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

## Maintainer Summary

- `/search` adds a single search surface for library and linked GitHub Markdown content.
- `/search_presets` adds persistent saved searches for library, GitHub, schedule, and global search.
- website schedule now supports a persistent `Full lecturer name` toggle for desktop table cards
- authorized website users can manage personal iCal subscription links from the schedule page
- active search sessions live in Redis
- saved presets live in `User.settings`
- scheduler Telegram delivery can use `PROXY_URL`

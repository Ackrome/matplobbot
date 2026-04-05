# Bot Search Features Wiki

This document describes the two bot-only search features added in the `P2 - Functional Improvements` section of `TODO.md`:

1. Unified global search via `/search`
2. Saved search presets via `/search_presets`

These features are implemented for the Telegram bot, not for the website frontend.

## 1. Unified Global Search

### Purpose

`/search` gives the user one search entry point that can search across:

- the internal `matplobblib` library
- Markdown notes from the user's linked GitHub repositories

The goal is to let the user search both knowledge sources at once and then open the matching result in the correct viewer without switching commands manually.

### Entry Points

Users can open unified search from:

- the `/search` command
- the bot command menu
- the `/help` menu button for unified search

### User Flow

1. The user sends `/search`.
2. The bot opens the global search panel and stores a fresh per-user search context in Redis.
3. The panel shows the currently enabled sources and available GitHub repository filters.
4. The user sends a plain text query.
5. The bot runs the search and edits the status message into a paginated result list.
6. The user can:
   - open a result
   - change enabled sources
   - limit GitHub search to selected linked repositories
   - save the current query and filters as a preset

### What Is Searched

#### Library source

The library side uses the semantic search engine with:

```text
source_type="lib"
```

Each result contains:

- `kind = "library"`
- `path`
- `score`

When the user taps a library result, the bot opens it through the normal library display flow.

#### GitHub source

The GitHub side searches only the repositories already linked to the current user in bot settings.

For each linked repository, the semantic search engine is called with:

```text
source_type=f"repo:{repo_path}"
```

Each GitHub result contains:

- `kind = "github"`
- `repo_path`
- `path`
- `score`

When the user taps a GitHub result, the bot opens the Markdown file through the GitHub display flow.

### Filters

The unified search UI supports two filter levels.

#### Source filters

The user can enable or disable:

- Library
- GitHub

Rules:

- At least one source must stay enabled.
- If the user tries to disable the last remaining source, the bot shows an alert instead of applying the change.

#### Repository filters

If GitHub is enabled and the user has linked repositories, the panel shows one toggle per linked repo.

Rules:

- Repository filters only affect GitHub results.
- The user can search any subset of linked repositories.
- If GitHub is enabled and no explicit repo subset exists yet, all linked repos are selected by default.
- If GitHub is disabled, the active repo list is cleared from the normalized filter state.

### Default State

When `/search` is opened:

- Library is enabled by default.
- GitHub is also enabled by default if the user has at least one linked repository.
- All linked repositories are selected by default.
- The initial panel appears before any query is run.

### Search Execution Details

The bot normalizes filters before every search so outdated or invalid repo selections are removed automatically.

The global search runs both source searches in parallel when both are enabled:

- library search: up to 20 results
- GitHub search: fetched per selected repository, then merged

The merged result list is sorted by:

1. semantic score descending
2. library-first on equal score

The final global result list is capped at 20 items.

GitHub results are deduplicated by Markdown file path within each repository before merging.

### Pagination

Global results use the normal bot pagination pattern.

- `SEARCH_RESULTS_PER_PAGE = 10`
- page navigation is inline
- pagination does not rerun the search; it only changes the current page view

### Result Presentation

The unified result list labels results by source:

- library results are shown as library items
- GitHub results are shown with the repository name and file path

Opening a result routes to the correct existing viewer:

- library result -> library content viewer
- GitHub result -> GitHub Markdown renderer/viewer

### Re-running on Filter Changes

If the user already has a query in the current `/search` session and then changes:

- enabled sources
- selected repositories

the bot immediately reruns the last query with the updated filters and refreshes the result list.

If no query has been entered yet, the bot only refreshes the panel text and buttons.

### Storage and Session Scope

The active unified search session is stored in Redis under the per-user cache key:

```text
global_search
```

The stored payload contains:

- `query`
- `filters`
- `results`

This cache powers:

- pagination
- source toggles
- repo toggles
- "save preset" actions
- reopening result items by index

### Limitations and Important Notes

- GitHub unified search only works for repositories linked in the user's bot settings.
- Unified search does not search arbitrary GitHub repositories.
- Unified search currently covers library content and linked GitHub Markdown content only. It does not include schedule entities.
- If the cached search context is gone, actions such as pagination or save-preset will fail gracefully with an "outdated/missing context" message.

## 2. Saved Search Presets

### Purpose

Saved presets let users store a reusable search configuration and reopen it later without retyping the query or rebuilding the filters manually.

This feature works for these bot search scopes:

- library search
- GitHub repository Markdown search
- schedule entity search
- unified global search

### Entry Points

Users can access presets from:

- the `/search_presets` command
- the bot command menu
- the `/help` menu button for search presets

Users can create presets from search result screens by tapping:

- `Save preset`

The button is available on these bot result screens:

- `/matp_search` results
- `/lec_search` results
- `/schedule` search results
- `/search` unified search results

The button appears only after a valid search result context has been created and cached.

### Supported Preset Types

Each preset stores a `search_kind` so the bot knows how to reopen it.

Supported values:

- `library`
- `github`
- `schedule`
- `global`

### What Exactly Gets Saved

#### Library preset

Saved data:

- search kind: `library`
- query text
- empty filters

Meaning:

- reruns the normal library semantic search

#### GitHub preset

Saved data:

- search kind: `github`
- query text
- `repo_paths` containing the one selected repository used for that search

Meaning:

- reruns GitHub Markdown search against the same linked repository

#### Schedule preset

Saved data:

- search kind: `schedule`
- query text
- `search_type`

Meaning:

- reruns schedule entity search with the same query and same mode
- the preset stores the search mode, not a chosen result item

Current schedule modes are the existing bot modes such as:

- group
- person
- auditorium

#### Global preset

Saved data:

- search kind: `global`
- query text
- source filter state
- selected linked GitHub repositories

Meaning:

- reruns unified search with the same source selection and repo subset

### How Users Save a Preset

1. The user performs a supported search and reaches a result screen.
2. The user taps `Save preset`.
3. The bot extracts the latest search context from Redis.
4. The bot asks the user to send a preset name.
5. The user sends a name.
6. The preset is stored in user settings and the bot immediately shows the presets list.

Important behavior:

- the preset is based on the latest cached search for that scope
- search results themselves are not stored inside the preset
- if the user tries to save after the cache is gone or outdated, the bot refuses the save action

Validation rules:

- the preset name is trimmed
- empty names are rejected
- the stored name is limited to 60 characters
- a preset cannot be saved if there is no current cached search context

### How Users Reopen a Preset

1. The user sends `/search_presets`.
2. The bot shows all saved presets in one inline list.
3. Each row shows:
   - a run button with a short scope label
   - a delete button
4. The user taps the run button.
5. The bot loads the preset and dispatches it to the matching search flow.

Scope labels used in the preset list:

- `LIB` for library presets
- `GH` for GitHub presets
- `SCH` for schedule presets
- `ALL` for unified global presets

### How Reopening Works Internally

#### Library preset execution

The bot reruns library semantic search and rebuilds the normal `lib_search` cache used by the library search result UI.

#### GitHub preset execution

The bot checks whether the saved repository is still linked for the user.

If the repository still exists:

- the bot reruns Markdown search for that repository
- the normal `md_search` cache is rebuilt

If the repository was removed from user settings:

- the bot warns the user that the saved repository is no longer linked
- the preset remains stored until the user deletes it

#### Schedule preset execution

The bot reruns schedule search with the saved:

- query
- search type

This uses the existing schedule search flow and rebuilds the `schedule_search` cache used by schedule result selection.

#### Global preset execution

The bot reruns unified search with the saved:

- query
- source toggles
- repository subset

The `global_search` cache is recreated so pagination and result opening work exactly like a fresh `/search` run.

### Deleting Presets

Users delete presets directly from the `/search_presets` list by tapping the delete button on a row.

Behavior:

- deletion removes the preset from persistent user settings
- the preset list message is refreshed in place
- if the preset no longer exists, the bot shows a safe "not found/outdated" response

### Persistence Model

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

### Ordering and Limits

Preset rules:

- presets are sorted by `updated_at`, falling back to `created_at`
- newest or most recently updated presets appear first
- the maximum stored preset count per user is `15`

If a future update path reuses an existing preset id, the preset is replaced and moved according to its new update timestamp.

### Cache Dependency

Creating a preset depends on the latest search cache still being available.

The save flow reads one of these per-user Redis cache keys:

- `lib_search`
- `md_search`
- `schedule_search`
- `global_search`

If the expected cache is missing or does not contain a valid query, the bot refuses to create the preset and tells the user there is no recent search to save.

### Operational Notes

- Presets are personal and not shared between users.
- Presets are language-neutral in storage. The same stored data can be reopened regardless of UI language.
- Presets do not snapshot search results; they only snapshot the query and filters. Reopening a preset runs a fresh search.
- A schedule preset saves the search request, not the final schedule entity selection.
- A GitHub preset becomes non-runnable if its repository is no longer linked, but it is still visible until deleted.

## Short Admin/Developer Summary

Feature summary for maintainers:

- `/search` adds a bot-side search center for library plus linked GitHub Markdown content.
- `/search_presets` adds persistent per-user saved searches for library, GitHub, schedule, and unified global search.
- active search sessions live in Redis
- saved presets live in `User.settings`
- both features are exposed through the command list and help menu

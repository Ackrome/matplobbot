# `frontend_i18n.js`

## Purpose

Loads the shared English and Russian frontend locale files and exposes one localization API for all static website pages.

## Public API

- `window.mpbI18n.ready` resolves after both locale requests have settled, including
  when one fails before the other completes. Available translations are applied
  together; failed loads are logged individually.
- `getLanguage()` returns the active `en` or `ru` locale.
- `setLanguage(locale)` persists and broadcasts a locale change.
- `t(key, fallback, params)` translates a key and interpolates `{name}` placeholders.
- `registerTranslator(callback)` registers a render callback and returns an unsubscribe function.

## Usage

Load this file before `navbar.js` or any page script that calls `window.mpbI18n`. Await `ready` before the first translation-sensitive render:

```js
await window.mpbI18n.ready;
title.textContent = window.mpbI18n.t("stats.title", "Statistics");
```

## Dependencies and side effects

The loader fetches `/locales/en.json?v=<LOCALE_VERSION>` and
`/locales/ru.json?v=<LOCALE_VERSION>` with HTTP revalidation, reads and writes
`localStorage.mpb_ui_lang`, updates `<html lang>`, and emits `mpb-language-change`.
Versioned requests bypass old workers' unversioned locale cache entries. The
current service worker handles locales with network first and falls back to the
latest runtime dictionary before considering the install snapshot. Dictionary
contents remain in the two JSON files; do not duplicate translations in JS.

## Maintenance

Keep locale key sets and placeholders identical. Keep `LOCALE_VERSION` aligned
with the precache locale URLs, and the loader URL aligned across all HTML callers
and the precache. Advance the service-worker cache version for these changes.
Run `tests/test_localization_completeness.py` after editing either JSON file or
cache/loading logic. Browser QA must include an already installed old worker:
clean contexts with service workers disabled cannot detect stale dictionaries.

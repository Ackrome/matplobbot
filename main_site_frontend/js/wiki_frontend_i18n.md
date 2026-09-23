# `frontend_i18n.js`

## Purpose

Loads the shared English and Russian frontend locale files and exposes one localization API for all static website pages.

## Public API

- `window.mpbI18n.ready` resolves after both locale files have been requested.
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

The loader fetches `/locales/en.json` and `/locales/ru.json`, reads and writes `localStorage.mpb_ui_lang`, updates `<html lang>`, and emits `mpb-language-change`.

## Maintenance

Keep locale key sets and placeholders identical. Run `tests/test_localization_completeness.py` after editing either JSON file, and update the service-worker cache version when changing locale assets or this loader.

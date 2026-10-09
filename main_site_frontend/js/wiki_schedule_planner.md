# Schedule comparison interface

`schedule_planner.js` powers the expandable planner on `/schedule`. Users add the current filtered schedule or search for more sources, select a date/time range and view conflicts and common free windows.

## Interface and usage

The module binds to `#schedulePlanner`, reads `window.schedulePageState` only when adding the open schedule, and posts bounded requests to `/api/schedule/plan`. It limits selections to six entities; backend validation enforces the 14-day range. No browser calculation overrides backend freshness decisions.

## Dependencies and effects

Uses the existing runtime API base and `mpbI18n` `plan.*` keys. Rendering uses text nodes for source data. It calls public read-only schedule search/comparison APIs and keeps selections in memory. It never creates a subscription or claims physical room availability.

## Maintenance

Keep omitted modules distinct from explicit empty module selections. Incomplete sources must suppress free windows and retain the visible warning. Verify desktop/mobile, language changes, date bounds, source failures and stale asynchronous responses.

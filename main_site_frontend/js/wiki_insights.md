# Stats outcome panels

`insights.js` adds operational and product summaries to the existing admin Stats page.

## Interface and usage

After `/api/auth/me` confirms the admin role, `#outcomeInsights` becomes visible. Expanding it or pressing Refresh loads `/api/insights/operations` and `/api/insights/product`. The period selector offers 7, 30 and 90 days. Tables distinguish no observations, stale jobs, failures and successful outcomes.

## Dependencies and effects

Uses the existing JWT, runtime API base, `mpbI18n` `insights.*` keys and `feature_panels.css`. It only reads aggregate endpoints. It does not send tracking events from the browser or retain user event payloads. Sign-out clears rendered data. Server authorization remains authoritative.

## Maintenance

Explain definitions alongside figures: active accounts cover instrumented workflows, repeat use means separate UTC dates, and successful Studio results count when opened. Do not turn missing observations into zero failures or imply a global cache timestamp proves all schedules are fresh. Verify role changes and races with in-flight requests.

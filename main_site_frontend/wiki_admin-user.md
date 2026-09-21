# admin-user.html

Static admin-only user details page opened from leaderboard rows on `/stats`.
The page is intentionally static; authorization and data access are enforced
by the protected stats API called by `js/admin-user.js`.

Maintenance: keep the API base loaded from `runtime_config.js`, and update the
cache-busting stylesheet version when the frontend's manual versioning policy
changes.

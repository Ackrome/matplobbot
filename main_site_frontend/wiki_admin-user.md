# admin-user.html

Static admin-only user details page opened from leaderboard rows on `/stats`.
The page is intentionally static; authorization and data access are enforced
by the protected stats API called by `js/admin-user.js`. After a successful
profile load, admins see a Telegram-like conversation with inbound and
outbound text bubbles, automatic polling, and a paginated older-message button.
The composer sends direct Telegram private messages through the protected
`send_message` endpoint and reports the server correlation id for audit tracing.

Maintenance: keep the API base loaded from `runtime_config.js`, and update the
cache-busting stylesheet version when the frontend's manual versioning policy
changes.

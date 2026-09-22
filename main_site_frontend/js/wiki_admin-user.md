# admin-user.js

Admin-only user detail page controller for the `/stats` leaderboard. It reads
the JWT from the existing frontend session and requests the protected
`/api/stats/users/{user_id}/profile` endpoint. Non-admin users receive a clear
authorization error and no user data is rendered.

The script is loaded by `admin-user.html`; it uses the standard Bearer token
for both the profile read and the admin-only
`POST /api/stats/users/{user_id}/send_message` action. The page loads the
paginated `/api/stats/users/{user_id}/messages` history, renders inbound and
outbound text messages as chat bubbles, offers older-page navigation, and polls
for new messages every ten seconds while visible. The composer validates
non-empty text, disables the submit button while the request is in flight, and
displays the returned correlation id or an error. Preserve HTML escaping for
message text/action details and keep API errors in text nodes rather than
injecting them as markup.

Maintenance: keep the response fields aligned with `UserProfileResponse` and
`UserMessageHistoryResponse`, preserve stable message ids for merging/polling,
and keep HTML escaping for message/action details.

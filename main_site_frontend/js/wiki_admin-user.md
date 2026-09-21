# admin-user.js

Admin-only user detail page controller for the `/stats` leaderboard. It reads
the JWT from the existing frontend session and requests the protected
`/api/stats/users/{user_id}/profile` endpoint. Non-admin users receive a clear
authorization error and no user data is rendered.

The script is loaded by `admin-user.html`; it does not send credentials to the
server outside the standard Bearer token and has no write side effects.

Maintenance: keep the response fields aligned with `UserProfileResponse` and
preserve HTML escaping for action details.

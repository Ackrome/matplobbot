# Account controls

`account.js` initializes the `/account` page. It loads the authenticated profile, downloads `/api/auth/account/export`, and submits `DELETE /api/auth/account` with an explicit `DELETE` confirmation and the short-lived export receipt. No public JavaScript API is exported.

The script depends on DOM IDs in `account.html`, the shared runtime API base and `mpbI18n`. It keeps the export receipt in memory only, verifies that the login token has not changed, expires the controls after 15 minutes, disables duplicate submissions and revokes blob URLs after download. The downloaded JSON includes Studio drafts from this browser under the current account's `mpb-studio-v1:${encodeURIComponent(accountId)}:` prefix. Complete deletion clears that prefix and the current website JWT, then updates navbar authentication. Other accounts' drafts remain untouched. Errors are rendered with `textContent`, and no account content is sent to analytics or logs.

After loading the authenticated profile it initializes `MpbAccountSubscriptions`.
Subscription errors stay in that section and must not disable data export or
change the export-before-delete account workflow.

For usage, sign in, download the export, type `DELETE` and acknowledge the irreversible scope. Maintain the API contract with auth-router tests and browser tests covering unsigned users, successful export, disabled confirmation, network failure, receipt expiry, deletion success, dark theme and mobile layout. Server-side receipt validation remains authoritative even if browser controls are modified.

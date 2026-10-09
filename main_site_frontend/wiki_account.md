# Account page

`account.html` provides the authenticated export-before-delete workflow at `/account`. Its sections explain the complete account scope, retained external data, and the separate Telegram-only operation in the bot. It uses the existing navbar, Tailwind stylesheet, theme bootstrap, runtime API base and shared locale dictionaries.

Usage: sign in, download the JSON export, save it, type `DELETE`, acknowledge the scope, then submit. Destructive controls remain disabled until a successful export. `js/account.js` owns all behavior; the HTML supplies semantic headings, labeled inputs, live feedback and mobile/dark-theme layout. It has no inline application script. When adding controls, preserve keyboard access and translate through the shared `account.*` locale keys. The page contains personal data and must not be added to the offline service-worker cache as an authenticated response.

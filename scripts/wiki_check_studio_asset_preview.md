# Studio asset browser regression

Run `node scripts/check_studio_asset_preview.mjs` after changing asset transport or
preview lifecycle. It uses the repository's installed Playwright Chromium and real
`studio.js` functions with editor startup disabled, plus an ephemeral loopback HTTP
fixture containing only a synthetic account token and images.

The test verifies a visible raster blob, Authorization header delivery, no JWT URL,
blob revocation, discarded late responses after switching projects, active-content
MIME rejection, and an unauthenticated direct asset navigation. It never contacts
production or uploads user data. The server/browser are closed in `finally`.

Backend tests in `test_studio_router_api.py` separately exercise the actual route's
ownership/authentication and response headers. This fixture does not replace full
Studio/CDN or release-stack browser acceptance. Requires npm dependencies and an
installed Playwright Chromium (`npx playwright install chromium`).

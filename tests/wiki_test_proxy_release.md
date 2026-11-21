# Proxy release tests

`TestProxyRelease` exercises immutable source validation, service-scoped
Compose arguments, SOCKS retries, and journal recovery after incomplete rollout.
The tests use private temporary JSON records and mock Docker. They depend on
`scripts/proxy_release.py` and its application release lock integration.

Run `python -m unittest tests.test_proxy_release`. Run the separate
`scripts/test_proxy_image.sh IMAGE` integration check for real SOCKS traffic
inside a disposable container. Keep the failure/recovery assertions in sync
with changes to the release state contract.

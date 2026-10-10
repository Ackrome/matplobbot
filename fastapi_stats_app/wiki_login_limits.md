# Password login limits

`enforce_login_limits(request, username)` must run before database lookup and
password hashing. It uses one atomic Redis Lua script for client, account and
client/account limits (60, 20 and 10 attempts per 60 seconds). Rejected traffic
does not extend a bucket's expiry. Keys contain only SHA-256 identifiers.

`client_identity(request)` traverses forwarded addresses from the trusted socket
peer. `AUTH_TRUSTED_PROXY_NETWORKS` configures trusted reverse-proxy CIDRs; deploy
with actual proxy networks and do not allow arbitrary public CIDRs. Untrusted
peers cannot choose their identity using headers. Direct and proxied entrances
must be exercised during release checks. Defaults cover local Caddy and Docker
bridge proxies. Redis failure returns 503 with Retry-After; there is no bypass
using the ordinary API limiter's fail-open option. Exceeding a limit returns 429.

Usage: `await enforce_login_limits(request, form_data.username)` in password
login. Dependencies: FastAPI, shared Redis client, Python ipaddress/asyncio.
Side effects are expiring Redis counters; no password or raw account identifiers
are logged. Maintain behavioral tests for shared throttling, bounded cooldown,
spoofed headers and outage behavior before altering thresholds.

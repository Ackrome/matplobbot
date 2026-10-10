"""Fail-closed shared limits before expensive password verification."""

import asyncio
import hashlib
import ipaddress
import logging
import os

from fastapi import HTTPException, Request

from shared_lib.redis_client import redis_client

logger = logging.getLogger(__name__)
# Both public entrances have trusted reverse proxies. Walk from the socket peer,
# never from the client-controlled leftmost X-Forwarded-For value.
TRUSTED_PROXIES = tuple(
    ipaddress.ip_network(value.strip())
    for value in os.getenv(
        "AUTH_TRUSTED_PROXY_NETWORKS", "127.0.0.0/8,::1/128,172.16.0.0/12"
    ).split(",")
    if value.strip()
)
WINDOW_SECONDS = 60
LIMITS = (60, 20, 10)  # client, account, client+account; bounded one-minute cooldown
_SCRIPT = """
local wait = 0
for i, key in ipairs(KEYS) do
    local count = redis.call('INCR', key)
    if count == 1 then redis.call('EXPIRE', key, ARGV[1]) end
    if count > tonumber(ARGV[i+1]) then
        wait = math.max(wait, redis.call('TTL', key))
    end
end
return wait
"""


def client_identity(request: Request) -> str:
    """Ignore spoofable forwarded fields unless every closer hop is trusted."""
    peer = request.client.host if request.client else "unknown"
    chain = [
        item.strip()
        for item in request.headers.get("x-forwarded-for", "").split(",")
        if item.strip()
    ]
    while chain:
        try:
            address = ipaddress.ip_address(peer)
        except ValueError:
            break
        if not any(address in network for network in TRUSTED_PROXIES):
            break
        peer = chain.pop()
    return peer


async def enforce_login_limits(request: Request, username: str) -> None:
    """Redis Lua makes increment/expiry atomic across API replicas; outage => 503."""
    client = client_identity(request)
    account = username.strip().casefold()[:256]
    values = (client, account, client + "\x00" + account)
    keys = [
        "auth:login:" + str(i) + ":" + hashlib.sha256(value.encode()).hexdigest()
        for i, value in enumerate(values)
    ]
    try:
        wait = int(
            await asyncio.wait_for(
                redis_client.client.eval(_SCRIPT, len(keys), *keys, WINDOW_SECONDS, *LIMITS),
                timeout=1.0,
            )
        )
    except Exception as exc:
        logger.warning("Login throttling unavailable (%s)", type(exc).__name__)
        raise HTTPException(
            503, "Sign-in is temporarily unavailable. Please retry.", headers={"Retry-After": "5"}
        ) from exc
    if wait > 0:
        raise HTTPException(
            429,
            "Too many sign-in attempts. Please retry shortly.",
            headers={"Retry-After": str(wait)},
        )

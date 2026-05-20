import asyncio
import hashlib
import logging
import math
import time
from typing import Any

from fastapi import HTTPException, Request, status

from shared_lib.redis_client import redis_client

from .config import (
    FASTAPI_RATE_LIMIT_BACKEND_COOLDOWN_SECONDS,
    FASTAPI_RATE_LIMIT_ENABLED,
    FASTAPI_RATE_LIMIT_FAIL_OPEN,
    FASTAPI_RATE_LIMIT_REDIS_TIMEOUT_SECONDS,
    RateLimitSettings,
)

logger = logging.getLogger(__name__)

_backend_unavailable_until = 0.0


def _current_user_identity(current_user: dict[str, Any] | None) -> str | None:
    if not current_user:
        return None

    for key in ("telegram_id", "id", "username"):
        value = current_user.get(key)
        if value:
            return f"user:{key}:{value}"

    db_obj = current_user.get("db_obj")
    for key in ("telegram_id", "id", "username"):
        value = getattr(db_obj, key, None)
        if value:
            return f"user:{key}:{value}"

    return None


def _request_identity(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first_hop = forwarded_for.split(",", maxsplit=1)[0].strip()
        if first_hop:
            return f"ip:{first_hop}"

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return f"ip:{real_ip.strip()}"

    if request.client and request.client.host:
        return f"ip:{request.client.host}"

    return "ip:unknown"


def _rate_limit_key(scope: str, identity: str, bucket: int) -> str:
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    safe_scope = "".join(ch if ch.isalnum() or ch in ":_-" else "_" for ch in scope)
    return f"rate_limit:api:{safe_scope}:{digest}:{bucket}"


async def _increment_counter(key: str, ttl_seconds: int) -> int:
    current_count = await redis_client.client.incr(key)
    if current_count == 1:
        await redis_client.client.expire(key, ttl_seconds)
    return int(current_count)


def _retry_after_seconds(now: float, window_seconds: int) -> int:
    remainder = window_seconds - (now % window_seconds)
    return max(1, math.ceil(remainder))


async def enforce_rate_limit(
    request: Request,
    *,
    scope: str,
    settings: RateLimitSettings,
    current_user: dict[str, Any] | None = None,
) -> None:
    """Apply a fixed-window Redis rate limit for one API scope."""
    global _backend_unavailable_until

    if not FASTAPI_RATE_LIMIT_ENABLED or settings.limit <= 0 or settings.window_seconds <= 0:
        return

    now = time.time()
    if _backend_unavailable_until > now:
        if FASTAPI_RATE_LIMIT_FAIL_OPEN:
            return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limit backend is temporarily unavailable.",
        )

    identity = _current_user_identity(current_user) or _request_identity(request)
    bucket = int(now) // settings.window_seconds
    key = _rate_limit_key(scope, identity, bucket)
    ttl_seconds = settings.window_seconds + 1

    try:
        current_count = await asyncio.wait_for(
            _increment_counter(key, ttl_seconds),
            timeout=FASTAPI_RATE_LIMIT_REDIS_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        if FASTAPI_RATE_LIMIT_BACKEND_COOLDOWN_SECONDS > 0:
            _backend_unavailable_until = now + FASTAPI_RATE_LIMIT_BACKEND_COOLDOWN_SECONDS
        logger.warning(
            "Rate limit backend unavailable for scope=%s identity=%s: %s",
            scope,
            identity,
            exc,
        )
        if FASTAPI_RATE_LIMIT_FAIL_OPEN:
            return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limit backend is unavailable.",
        ) from exc

    if current_count <= settings.limit:
        return

    retry_after = _retry_after_seconds(now, settings.window_seconds)
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=(
            f"Rate limit exceeded for {scope}. "
            f"Allowed {settings.limit} request(s) per {settings.window_seconds} seconds."
        ),
        headers={"Retry-After": str(retry_after)},
    )

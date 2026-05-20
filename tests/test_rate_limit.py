from __future__ import annotations

import unittest
from unittest.mock import patch

FASTAPI_AVAILABLE = True
try:
    from fastapi import HTTPException
    from starlette.requests import Request

    from fastapi_stats_app import rate_limit
    from fastapi_stats_app.config import RateLimitSettings
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False


class _FakeRedisCommands:
    def __init__(self):
        self.counts: dict[str, int] = {}
        self.expirations: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, ttl: int) -> None:
        self.expirations[key] = ttl


class _BrokenRedisCommands:
    async def incr(self, key: str) -> int:
        raise RuntimeError("redis unavailable")

    async def expire(self, key: str, ttl: int) -> None:
        raise AssertionError("expire should not be called after incr failure")


def _request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/schedule/search",
            "headers": headers or [],
            "client": ("127.0.0.1", 49152),
        }
    )


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class TestRateLimit(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        rate_limit._backend_unavailable_until = 0.0

    async def test_redis_counter_blocks_after_limit(self):
        fake_redis = _FakeRedisCommands()

        with (
            patch.object(rate_limit.redis_client, "client", fake_redis),
            patch.object(rate_limit, "FASTAPI_RATE_LIMIT_ENABLED", True),
            patch.object(rate_limit, "FASTAPI_RATE_LIMIT_FAIL_OPEN", True),
            patch.object(rate_limit, "FASTAPI_RATE_LIMIT_REDIS_TIMEOUT_SECONDS", 1.0),
            patch.object(rate_limit.time, "time", return_value=120.0),
        ):
            await rate_limit.enforce_rate_limit(
                _request(headers=[(b"x-forwarded-for", b"203.0.113.10")]),
                scope="schedule_search",
                settings=RateLimitSettings(limit=1, window_seconds=60),
            )

            with self.assertRaises(HTTPException) as ctx:
                await rate_limit.enforce_rate_limit(
                    _request(headers=[(b"x-forwarded-for", b"203.0.113.10")]),
                    scope="schedule_search",
                    settings=RateLimitSettings(limit=1, window_seconds=60),
                )

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(ctx.exception.headers.get("Retry-After"), "60")
        self.assertEqual(len(fake_redis.counts), 1)
        self.assertEqual(next(iter(fake_redis.expirations.values())), 61)

    async def test_unavailable_redis_fails_open_by_default(self):
        broken_redis = _BrokenRedisCommands()

        with (
            patch.object(rate_limit.redis_client, "client", broken_redis),
            patch.object(rate_limit, "FASTAPI_RATE_LIMIT_ENABLED", True),
            patch.object(rate_limit, "FASTAPI_RATE_LIMIT_FAIL_OPEN", True),
            patch.object(rate_limit, "FASTAPI_RATE_LIMIT_REDIS_TIMEOUT_SECONDS", 1.0),
            patch.object(rate_limit, "FASTAPI_RATE_LIMIT_BACKEND_COOLDOWN_SECONDS", 0.0),
        ):
            await rate_limit.enforce_rate_limit(
                _request(),
                scope="studio_compile",
                settings=RateLimitSettings(limit=1, window_seconds=60),
                current_user={"id": 7},
            )

import os
import unittest
from unittest.mock import AsyncMock, patch

FASTAPI_AVAILABLE = True
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-unit-tests")
    from fastapi_stats_app.routers import stats_router  # noqa: E402
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False


class _FakeTelegramResponse:
    def __init__(self, status: int = 200, body: str = "ok"):
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self):
        return self._body


class _FakeTelegramSession:
    def __init__(self, response: _FakeTelegramResponse):
        self.response = response
        self.post_calls: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def post(self, url: str, json: dict):
        self.post_calls.append((url, json))
        return self.response


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class TestStatsSendMessageAPI(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(stats_router.router, prefix="/api")
        self.client = TestClient(self.app)
        self.app.dependency_overrides[stats_router.require_admin] = lambda: {
            "id": 10,
            "telegram_id": 777,
            "role": "admin",
        }

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_send_message_success(self):
        fake_session = _FakeTelegramSession(_FakeTelegramResponse(status=200))
        with (
            patch.object(stats_router, "BOT_TOKEN", "test-token"),
            patch.object(
                stats_router,
                "_enforce_send_message_rate_limit",
                new=AsyncMock(return_value=None),
            ) as mocked_rate_limit,
            patch.object(
                stats_router,
                "log_user_action",
                new=AsyncMock(return_value=None),
            ) as mocked_log_action,
            patch.object(
                stats_router,
                "_emit_admin_send_audit",
            ) as mocked_audit,
            patch.object(
                stats_router.aiohttp,
                "ClientSession",
                return_value=fake_session,
            ),
        ):
            response = self.client.post(
                "/api/stats/users/123/send_message",
                json={"text": "hello"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertIn("correlation_id", payload)
        mocked_rate_limit.assert_awaited_once_with(777)
        mocked_log_action.assert_awaited_once()
        self.assertGreaterEqual(mocked_audit.call_count, 1)

    def test_send_message_rate_limited(self):
        with (
            patch.object(stats_router, "BOT_TOKEN", "test-token"),
            patch.object(
                stats_router,
                "_enforce_send_message_rate_limit",
                new=AsyncMock(
                    side_effect=HTTPException(status_code=429, detail="rate limited for test")
                ),
            ),
            patch.object(stats_router, "_emit_admin_send_audit") as mocked_audit,
            patch.object(stats_router.aiohttp, "ClientSession") as mocked_client_session,
        ):
            response = self.client.post(
                "/api/stats/users/123/send_message",
                json={"text": "hello"},
            )

        self.assertEqual(response.status_code, 429)
        mocked_client_session.assert_not_called()
        self.assertGreaterEqual(mocked_audit.call_count, 1)

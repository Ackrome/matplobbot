import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

FASTAPI_AVAILABLE = True
try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-unit-tests")

    fake_schedule_service = types.ModuleType("shared_lib.services.schedule_service")
    fake_schedule_service.generate_ical_from_aggregated_schedule = lambda *args, **kwargs: b""
    fake_schedule_service.get_aggregated_schedule = AsyncMock(return_value=[])

    with patch.dict(
        sys.modules,
        {"shared_lib.services.schedule_service": fake_schedule_service},
    ):
        from fastapi_stats_app.routers import calendar_router  # noqa: E402
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class TestCalendarAPI(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(calendar_router.router, prefix="/api")
        self.client = TestClient(self.app)

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def _override_user(self, telegram_id):
        self.app.dependency_overrides[calendar_router.get_current_user] = lambda: {
            "id": 1,
            "role": "user",
            "telegram_id": telegram_id,
        }

    def test_get_subscription_returns_links_for_telegram_user(self):
        self._override_user(12345)

        with (
            patch.object(calendar_router, "PUBLIC_API_URL", "https://api.example.com"),
            patch.object(
                calendar_router,
                "get_or_create_calendar_secret",
                AsyncMock(return_value="secret123"),
            ) as get_secret,
        ):
            response = self.client.get("/api/cal/subscription")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "enabled": True,
                "http_url": "https://api.example.com/api/cal/secret123.ics",
                "webcal_url": "webcal://api.example.com/api/cal/secret123.ics",
            },
        )
        get_secret.assert_awaited_once_with(12345)

    def test_get_subscription_returns_disabled_for_non_telegram_account(self):
        self._override_user(None)

        with patch.object(
            calendar_router,
            "get_or_create_calendar_secret",
            AsyncMock(),
        ) as get_secret:
            response = self.client.get("/api/cal/subscription")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "enabled": False,
                "http_url": None,
                "webcal_url": None,
            },
        )
        get_secret.assert_not_awaited()

    def test_reset_subscription_rotates_secret_for_telegram_user(self):
        self._override_user(54321)

        with (
            patch.object(calendar_router, "PUBLIC_API_URL", "https://api.example.com"),
            patch.object(
                calendar_router,
                "regenerate_calendar_secret",
                AsyncMock(return_value="secret456"),
            ) as regenerate_secret,
        ):
            response = self.client.post("/api/cal/subscription/reset")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "enabled": True,
                "http_url": "https://api.example.com/api/cal/secret456.ics",
                "webcal_url": "webcal://api.example.com/api/cal/secret456.ics",
            },
        )
        regenerate_secret.assert_awaited_once_with(54321)

    def test_reset_subscription_requires_telegram_link(self):
        self._override_user(None)

        with patch.object(
            calendar_router,
            "regenerate_calendar_secret",
            AsyncMock(),
        ) as regenerate_secret:
            response = self.client.post("/api/cal/subscription/reset")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"detail": "Calendar subscription is unavailable for this account"},
        )
        regenerate_secret.assert_not_awaited()

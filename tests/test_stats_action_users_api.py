import os
import unittest
from unittest.mock import AsyncMock, patch

FASTAPI_AVAILABLE = True
try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-unit-tests")
    from fastapi_stats_app.routers import stats_router  # noqa: E402
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class TestStatsActionUsersAPI(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(stats_router.router, prefix="/api")
        self.client = TestClient(self.app)
        self.app.dependency_overrides[stats_router.require_admin] = lambda: {
            "id": 1,
            "role": "admin",
        }
        self.app.dependency_overrides[stats_router.get_db_session_dependency] = lambda: object()

    def tearDown(self):
        self.app.dependency_overrides.clear()

    @staticmethod
    def _fake_db_result():
        return {
            "users": [
                {
                    "user_id": 101,
                    "full_name": "Test User",
                    "username": "test_user",
                    "avatar_pic_url": None,
                    "actions_count": 3,
                }
            ],
            "total_users": 1,
        }

    def test_action_users_canonical_route(self):
        with patch.object(
            stats_router,
            "get_users_for_action",
            new=AsyncMock(return_value=self._fake_db_result()),
        ):
            response = self.client.get(
                "/api/stats/action_users",
                params={"action_type": "command", "action_details": "/start"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["users"]), 1)
        self.assertEqual(payload["users"][0]["user_id"], 101)
        self.assertEqual(payload["pagination"]["current_page"], 1)

    def test_action_users_legacy_route_alias(self):
        with patch.object(
            stats_router,
            "get_users_for_action",
            new=AsyncMock(return_value=self._fake_db_result()),
        ):
            response = self.client.get(
                "/api/stats/stats/action_users",
                params={"action_type": "command", "action_details": "/start"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["users"]), 1)
        self.assertEqual(payload["users"][0]["full_name"], "Test User")

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


class _SessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class TestStatsLeaderboardAPI(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(stats_router.router, prefix="/api")
        self.client = TestClient(self.app)

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_leaderboard_contract_for_admin(self):
        payload = [
            {
                "user_id": 1,
                "full_name": "Admin User",
                "username": "admin",
                "avatar_pic_url": None,
                "actions_count": 42,
                "last_action_time": "2026-04-04 12:00:00",
            }
        ]
        self.app.dependency_overrides[stats_router.require_admin] = lambda: {"id": 1, "role": "admin"}

        with (
            patch.object(stats_router, "get_session", return_value=_SessionContext(object())),
            patch.object(
                stats_router, "get_leaderboard_data_from_db", new=AsyncMock(return_value=payload)
            ),
        ):
            response = self.client.get("/api/stats/leaderboard")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data, payload)
        self.assertEqual(
            set(data[0].keys()),
            {
                "user_id",
                "full_name",
                "username",
                "avatar_pic_url",
                "actions_count",
                "last_action_time",
            },
        )

    def test_leaderboard_empty_state(self):
        self.app.dependency_overrides[stats_router.require_admin] = lambda: {"id": 1, "role": "admin"}

        with (
            patch.object(stats_router, "get_session", return_value=_SessionContext(object())),
            patch.object(stats_router, "get_leaderboard_data_from_db", new=AsyncMock(return_value=[])),
        ):
            response = self.client.get("/api/stats/leaderboard")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_leaderboard_returns_500_on_backend_error(self):
        self.app.dependency_overrides[stats_router.require_admin] = lambda: {"id": 1, "role": "admin"}

        with (
            patch.object(stats_router, "get_session", return_value=_SessionContext(object())),
            patch.object(
                stats_router,
                "get_leaderboard_data_from_db",
                new=AsyncMock(side_effect=RuntimeError("db failed")),
            ),
        ):
            response = self.client.get("/api/stats/leaderboard")

        self.assertEqual(response.status_code, 500)

    def test_leaderboard_rejects_non_admin(self):
        def deny_admin():
            raise HTTPException(status_code=403, detail="Admin access required")

        self.app.dependency_overrides[stats_router.require_admin] = deny_admin

        response = self.client.get("/api/stats/leaderboard")

        self.assertEqual(response.status_code, 403)

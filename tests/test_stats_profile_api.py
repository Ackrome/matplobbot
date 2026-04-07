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
class TestStatsProfileAPI(unittest.TestCase):
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
    def _fake_profile_result():
        return {
            "user_details": {
                "user_id": 42,
                "full_name": "Test User",
                "username": "tester",
                "avatar_pic_url": None,
                "total_actions": 3,
            },
            "actions": [
                {
                    "id": 100,
                    "action_type": "command",
                    "action_details": "/start",
                    "timestamp": "2026-04-07 10:00:00",
                }
            ],
            "total_actions": 3,
        }

    def test_profile_pagination_sort_matrix(self):
        with (
            patch.object(
                stats_router,
                "get_user_profile_data_from_db",
                new=AsyncMock(return_value=self._fake_profile_result()),
            ) as mocked_get_profile,
            patch.object(stats_router.redis_client, "get_cache", new=AsyncMock(return_value=None)),
            patch.object(stats_router.redis_client, "set_cache", new=AsyncMock(return_value=None)),
        ):
            matrix = [
                ("timestamp", "desc", 1, 50),
                ("timestamp", "asc", 2, 20),
                ("id", "desc", 3, 10),
                ("action_type", "asc", 1, 25),
                ("action_details", "desc", 2, 15),
            ]

            for sort_by, sort_order, page, page_size in matrix:
                response = self.client.get(
                    "/api/stats/users/42/profile",
                    params={
                        "page": page,
                        "page_size": page_size,
                        "sort_by": sort_by,
                        "sort_order": sort_order,
                    },
                )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["pagination"]["sort_by"], sort_by)
                self.assertEqual(payload["pagination"]["sort_order"], sort_order)
                self.assertEqual(payload["pagination"]["current_page"], page)
                self.assertEqual(payload["pagination"]["page_size"], page_size)

            self.assertEqual(mocked_get_profile.await_count, len(matrix))

    def test_profile_rejects_invalid_sort_by(self):
        response = self.client.get(
            "/api/stats/users/42/profile",
            params={"sort_by": "drop_table"},
        )
        self.assertEqual(response.status_code, 422)

    def test_profile_rejects_invalid_sort_order(self):
        response = self.client.get(
            "/api/stats/users/42/profile",
            params={"sort_order": "sideways"},
        )
        self.assertEqual(response.status_code, 422)

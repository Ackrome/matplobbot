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

    def test_action_users_pagination_sort_matrix(self):
        with patch.object(
            stats_router,
            "get_users_for_action",
            new=AsyncMock(return_value=self._fake_db_result()),
        ) as mocked_get_action_users:
            matrix = [
                ("full_name", "asc", 1, 15),
                ("full_name", "desc", 2, 10),
                ("user_id", "asc", 3, 5),
                ("username", "desc", 1, 20),
            ]
            for sort_by, sort_order, page, page_size in matrix:
                response = self.client.get(
                    "/api/stats/action_users",
                    params={
                        "action_type": "command",
                        "action_details": "/start",
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

            self.assertEqual(mocked_get_action_users.await_count, len(matrix))

    def test_action_users_rejects_invalid_sort_by(self):
        response = self.client.get(
            "/api/stats/action_users",
            params={
                "action_type": "command",
                "action_details": "/start",
                "sort_by": "unsafe_sql",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_action_users_rejects_invalid_sort_order(self):
        response = self.client.get(
            "/api/stats/action_users",
            params={
                "action_type": "command",
                "action_details": "/start",
                "sort_order": "drop_table",
            },
        )
        self.assertEqual(response.status_code, 422)

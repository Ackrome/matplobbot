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
class TestStatsExportAPI(unittest.TestCase):
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

    def test_export_actions_json_default(self):
        fake_actions = [
            {
                "id": 1,
                "action_type": "command",
                "action_details": "/start",
                "timestamp": "2026-04-06 10:00:00",
            }
        ]
        with patch.object(
            stats_router, "get_all_user_actions", new=AsyncMock(return_value=fake_actions)
        ):
            response = self.client.get("/api/stats/users/1/export_actions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"actions": fake_actions})

    def test_export_actions_csv(self):
        fake_actions = [
            {
                "id": 7,
                "action_type": "text_message",
                "action_details": "hello",
                "timestamp": "2026-04-05 09:15:00",
            }
        ]
        with patch.object(
            stats_router, "get_all_user_actions", new=AsyncMock(return_value=fake_actions)
        ):
            response = self.client.get("/api/stats/users/1/export_actions?format=csv")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers.get("content-type", ""))
        self.assertIn("attachment; filename=", response.headers.get("content-disposition", ""))
        self.assertIn("action_type", response.text)
        self.assertIn("text_message", response.text)

    def test_export_actions_weekly_pdf(self):
        fake_actions = [
            {
                "id": 9,
                "action_type": "callback_query",
                "action_details": "mysch_day",
                "timestamp": "2026-04-06 11:00:00",
            }
        ]
        with (
            patch.object(
                stats_router, "get_all_user_actions", new=AsyncMock(return_value=fake_actions)
            ),
            patch.object(stats_router, "_build_weekly_pdf_bytes", return_value=b"%PDF-1.4\nfake"),
        ):
            response = self.client.get("/api/stats/users/1/export_actions?format=weekly_pdf")

        self.assertEqual(response.status_code, 200)
        self.assertIn("application/pdf", response.headers.get("content-type", ""))
        self.assertIn("attachment; filename=", response.headers.get("content-disposition", ""))
        self.assertTrue(response.content.startswith(b"%PDF-1.4"))

    def test_export_actions_rejects_unknown_format(self):
        with patch.object(stats_router, "get_all_user_actions", new=AsyncMock(return_value=[])):
            response = self.client.get("/api/stats/users/1/export_actions?format=xml")

        self.assertEqual(response.status_code, 400)

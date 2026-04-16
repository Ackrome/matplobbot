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
class TestStatsProxyDiagnosticsAPI(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(stats_router.router, prefix="/api")
        self.client = TestClient(self.app)
        self.app.dependency_overrides[stats_router.require_admin] = lambda: {
            "id": 1,
            "role": "admin",
        }

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_proxy_diagnostics_returns_normalized_summary(self):
        summary_payload = {
            "state": {
                "last_build": {
                    "merged_entries": 7,
                    "outline_entries": 2,
                    "subscription_entries": 5,
                }
            },
            "telegram": {
                "group": "TELEGRAM-AUTO",
                "selected": "tg-fast",
                "candidate_count": 2,
                "top_candidates": [
                    {"name": "tg-fast", "alive": True, "delay": 91},
                    {"name": "tg-backup", "alive": False, "delay": 140},
                ],
            },
            "openai": {
                "group": "OPENAI-AUTO",
                "selected": "oa-main",
                "candidate_count": 1,
                "top_candidates": [
                    {"name": "oa-main", "alive": True, "delay": 115},
                ],
            },
        }

        with patch.object(
            stats_router,
            "_fetch_proxy_summary_payload",
            new=AsyncMock(return_value=(summary_payload, "http://proxy:8080/summary", None)),
        ):
            response = self.client.get("/api/stats/proxy_diagnostics")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["available"])
        self.assertEqual(body["source_url"], "http://proxy:8080/summary")
        self.assertEqual(body["last_build"]["merged_entries"], 7)
        self.assertEqual(body["telegram"]["selected"], "tg-fast")
        self.assertTrue(body["telegram"]["top_candidates"][0]["selected"])
        self.assertFalse(body["telegram"]["top_candidates"][1]["selected"])
        self.assertEqual(body["openai"]["top_candidates"][0]["delay"], 115.0)

    def test_proxy_diagnostics_returns_soft_failure_payload(self):
        with patch.object(
            stats_router,
            "_fetch_proxy_summary_payload",
            new=AsyncMock(return_value=(None, None, "proxy cleaner unavailable")),
        ):
            response = self.client.get("/api/stats/proxy_diagnostics")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["available"])
        self.assertEqual(body["error"], "proxy cleaner unavailable")
        self.assertEqual(body["telegram"]["group"], "TELEGRAM-AUTO")
        self.assertEqual(body["openai"]["candidate_count"], 0)

    def test_proxy_diagnostics_openapi_uses_typed_schema(self):
        schema = self.app.openapi()

        proxy_schema = schema["paths"]["/api/stats/proxy_diagnostics"]["get"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]
        self.assertEqual(proxy_schema["$ref"], "#/components/schemas/ProxyDiagnosticsResponse")

import os
import sys
import types
import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

FASTAPI_AVAILABLE = True
try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-unit-tests")

    fake_schedule_service = types.ModuleType("shared_lib.services.schedule_service")
    fake_schedule_service.get_module_name = lambda *_args, **_kwargs: None
    fake_schedule_service.get_schedule_with_cache_fallback = AsyncMock(return_value=([], False))
    fake_schedule_service.get_schedule_fallback_counters = AsyncMock(return_value={})
    fake_schedule_service.get_unique_modules_hybrid = AsyncMock(return_value=[])

    with patch.dict(
        sys.modules,
        {"shared_lib.services.schedule_service": fake_schedule_service},
    ):
        from fastapi_stats_app.routers import schedule_router  # noqa: E402
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class TestScheduleSearchAPI(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(schedule_router.router, prefix="/api")
        self.client = TestClient(self.app)
        self.fake_db = AsyncMock()
        self.app.dependency_overrides[schedule_router.get_db_session_dependency] = (
            lambda: self.fake_db
        )
        self.app.dependency_overrides[schedule_router.get_shared_http_session] = lambda: object()

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_search_without_type_combines_groups_people_and_auditoriums(self):
        fake_client = types.SimpleNamespace(
            search=AsyncMock(
                side_effect=[
                    [{"id": "group-1", "label": "M80-101"}],
                    [{"id": "person-1", "label": "Ivan Petrov"}],
                    [{"id": "room-1", "label": "A-101"}],
                ]
            )
        )

        with patch.object(schedule_router, "create_ruz_api_client", return_value=fake_client):
            response = self.client.get("/api/schedule/search", params={"term": "ivan"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {
                    "id": "group-1",
                    "label": "M80-101",
                    "description": "Group",
                    "type": "group",
                    "is_offline": False,
                },
                {
                    "id": "person-1",
                    "label": "Ivan Petrov",
                    "description": "Lecturer",
                    "type": "person",
                    "is_offline": False,
                },
                {
                    "id": "room-1",
                    "label": "A-101",
                    "description": "Auditorium",
                    "type": "auditorium",
                    "is_offline": False,
                },
            ],
        )

    def test_search_without_type_uses_cache_when_one_search_kind_is_unavailable(self):
        fake_client = types.SimpleNamespace(
            search=AsyncMock(
                side_effect=[
                    [{"id": "group-1", "label": "M80-101"}],
                    schedule_router.RuzAPIError("person search failed"),
                    [],
                ]
            )
        )

        cache_side_effect = [
            [
                {
                    "id": "person-1",
                    "label": "Ivan Petrov",
                    "description": "Lecturer (cached)",
                    "type": "person",
                    "is_offline": True,
                }
            ]
        ]

        with (
            patch.object(schedule_router, "create_ruz_api_client", return_value=fake_client),
            patch.object(
                schedule_router,
                "search_cached_entities",
                AsyncMock(side_effect=cache_side_effect),
            ) as cached_search,
        ):
            response = self.client.get("/api/schedule/search", params={"term": "ivan"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 2)
        self.assertEqual(payload[0]["type"], "group")
        self.assertEqual(payload[1]["type"], "person")
        self.assertTrue(payload[1]["is_offline"])
        cached_search.assert_awaited_once_with(self.fake_db, "ivan", "person")

    def test_search_without_type_returns_503_when_all_sources_are_unavailable(self):
        fake_client = types.SimpleNamespace(
            search=AsyncMock(
                side_effect=[
                    schedule_router.RuzAPIError("group search failed"),
                    schedule_router.RuzAPIError("person search failed"),
                    schedule_router.RuzAPIError("auditorium search failed"),
                ]
            )
        )

        with (
            patch.object(schedule_router, "create_ruz_api_client", return_value=fake_client),
            patch.object(
                schedule_router,
                "search_cached_entities",
                AsyncMock(return_value=[]),
            ),
        ):
            response = self.client.get("/api/schedule/search", params={"term": "ivan"})

        self.assertEqual(response.status_code, 503)

    def test_schedule_data_includes_source_updated_at(self):
        fake_schedule = [
            {
                "date": "2026-04-06",
                "discipline": "Math",
                "group": "M80-101",
                "beginLesson": "10:10",
                "endLesson": "11:40",
                "auditorium": "A-101",
                "kindOfWork": "Lecture",
            }
        ]
        parsed_at = datetime(2026, 4, 6, 10, 30, tzinfo=UTC)

        with (
            patch.object(schedule_router, "create_ruz_api_client", return_value=object()),
            patch.object(
                schedule_router,
                "get_schedule_with_cache_fallback",
                AsyncMock(return_value=(fake_schedule, False)),
            ),
            patch.object(schedule_router, "get_all_short_names", AsyncMock(return_value={})),
            patch.object(schedule_router, "get_discipline_modules_map", AsyncMock(return_value={})),
            patch.object(schedule_router, "get_unique_modules_hybrid", AsyncMock(return_value=[])),
            patch.object(
                schedule_router,
                "get_cached_schedule_updated_at",
                AsyncMock(return_value=parsed_at),
            ),
        ):
            response = self.client.get("/api/schedule/data/group/group-1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source_updated_at"], parsed_at.isoformat())

    def test_schedule_fallback_counters_endpoint(self):
        self.app.dependency_overrides[schedule_router.require_admin] = lambda: {
            "id": 1,
            "role": "admin",
        }
        with patch.object(
            schedule_router,
            "get_schedule_fallback_counters",
            AsyncMock(
                return_value={
                    "ruz_api_success": 10,
                    "cache_fallback": 3,
                    "no_cache": 1,
                }
            ),
        ):
            response = self.client.get("/api/schedule/fallback_counters")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "ruz_api_success": 10,
                "cache_fallback": 3,
                "no_cache": 1,
            },
        )

    def test_schedule_data_rejects_invalid_base_date(self):
        response = self.client.get(
            "/api/schedule/data/group/group-1",
            params={"base_date": "2026/04/06"},
        )

        self.assertEqual(response.status_code, 422)
        detail = response.json().get("detail", [])
        self.assertTrue(any(item.get("loc", [])[-1] == "base_date" for item in detail))

    def test_schedule_search_openapi_documents_aliases(self):
        schema = self.app.openapi()
        params = schema["paths"]["/api/schedule/search"]["get"]["parameters"]
        type_param = next(
            (param for param in params if param.get("name") == "type"),
            None,
        )
        self.assertIsNotNone(type_param)
        description = str(type_param.get("description", "")).lower()
        self.assertIn("lecturer", description)
        self.assertIn("teacher", description)
        self.assertIn("room", description)
        examples = type_param.get("schema", {}).get("examples", [])
        self.assertIn("lecturer", examples)
        self.assertIn("teacher", examples)
        self.assertIn("room", examples)

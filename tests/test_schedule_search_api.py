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
    fake_schedule_service.get_module_name = lambda *_args, **_kwargs: None
    fake_schedule_service.get_schedule_with_cache_fallback = AsyncMock(return_value=([], False))
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
        self.app.dependency_overrides[schedule_router.get_db_session_dependency] = lambda: self.fake_db
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


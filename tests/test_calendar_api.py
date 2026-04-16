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
    fake_schedule_service.generate_ical_from_aggregated_schedule = lambda *args, **kwargs: b""
    fake_schedule_service.get_aggregated_schedule = AsyncMock(return_value=[])
    fake_schedule_service.generate_profile_ical_from_aggregated_schedule = (
        lambda *args, **kwargs: b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"
    )
    fake_schedule_service.get_calendar_aggregated_schedule = AsyncMock(return_value=[])
    fake_schedule_service.get_schedule_with_cache_fallback = AsyncMock(return_value=([], False))
    fake_schedule_service.get_semester_bounds = lambda: ("2026-02-01", "2026-07-15")

    with patch.dict(
        sys.modules,
        {"shared_lib.services.schedule_service": fake_schedule_service},
    ):
        from fastapi_stats_app.routers import calendar_router_v2 as calendar_router  # noqa: E402
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class TestCalendarAPI(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(calendar_router.router, prefix="/api")
        self.client = TestClient(self.app)
        self.fake_db = AsyncMock()
        self.fake_db.add = lambda _obj: None
        self.fake_db.commit = AsyncMock()
        self.fake_db.refresh = AsyncMock()
        self.app.dependency_overrides[calendar_router.get_db_session_dependency] = (
            lambda: self.fake_db
        )

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def _override_user(self, telegram_id, preferences=None, db_obj=None):
        self.app.dependency_overrides[calendar_router.get_current_user] = lambda: {
            "id": 1,
            "role": "user",
            "telegram_id": telegram_id,
            "preferences": preferences or {},
            "db_obj": db_obj,
        }

    def test_get_subscription_returns_links_for_telegram_user(self):
        self._override_user(12345, preferences={})
        active_subscriptions = [
            {
                "id": 10,
                "is_active": True,
                "entity_type": "group",
                "entity_id": "group-1",
                "entity_name": "Group 1",
            }
        ]
        sample_schedule = [
            {
                "date": "2026-04-07",
                "beginLesson": "10:10",
                "endLesson": "11:40",
                "discipline": "Physics",
                "kindOfWork": "Lecture",
                "source_entity": "Group 1",
                "source_entity_type": "group",
                "source_entity_id": "group-1",
                "simple_type": "Lecture",
                "module": "Core",
            }
        ]

        with (
            patch.object(calendar_router, "PUBLIC_API_URL", "https://api.example.com"),
            patch.object(
                calendar_router,
                "get_or_create_calendar_secret",
                AsyncMock(return_value="abcdef1234567890abcdef1234567890"),
            ) as get_secret,
            patch.object(
                calendar_router,
                "get_user_subscriptions",
                AsyncMock(return_value=(active_subscriptions, 1)),
            ),
            patch.object(
                calendar_router,
                "get_calendar_aggregated_schedule",
                AsyncMock(return_value=sample_schedule),
            ),
            patch.object(
                calendar_router,
                "_get_source_update_map",
                AsyncMock(return_value={("group", "group-1"): datetime(2026, 4, 6, tzinfo=UTC)}),
            ),
        ):
            response = self.client.get("/api/cal/subscription")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["enabled"])
        self.assertTrue(payload["sync_enabled"])
        self.assertEqual(payload["selected_profile_id"], "all")
        self.assertEqual(
            payload["http_url"],
            "https://api.example.com/api/cal/abcdef1234567890abcdef1234567890.ics",
        )
        self.assertEqual(
            payload["webcal_url"],
            "webcal://api.example.com/api/cal/abcdef1234567890abcdef1234567890.ics",
        )
        self.assertIn("...", payload["masked_http_url"])
        self.assertEqual(payload["source_summary"]["active_subscriptions"], 1)
        self.assertGreaterEqual(len(payload["profiles"]), 2)
        self.assertEqual(payload["profiles"][0]["health"]["event_count"], 1)
        get_secret.assert_awaited_once_with(12345)

    def test_get_subscription_returns_disabled_for_non_telegram_account(self):
        self._override_user(None, preferences={})

        with patch.object(
            calendar_router,
            "get_or_create_calendar_secret",
            AsyncMock(),
        ) as get_secret:
            response = self.client.get("/api/cal/subscription")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["enabled"])
        self.assertFalse(payload["eligibility"]["has_telegram_link"])
        self.assertIn("telegram_link_required", payload["eligibility"]["reasons"])
        self.assertGreaterEqual(len(payload["profiles"]), 2)
        get_secret.assert_not_awaited()

    def test_reset_subscription_rotates_secret_for_telegram_user(self):
        self._override_user(54321, preferences={})
        active_subscriptions = [
            {
                "id": 11,
                "is_active": True,
                "entity_type": "group",
                "entity_id": "group-1",
                "entity_name": "Group 1",
            }
        ]

        with (
            patch.object(calendar_router, "PUBLIC_API_URL", "https://api.example.com"),
            patch.object(
                calendar_router,
                "regenerate_calendar_secret",
                AsyncMock(return_value="fedcba0987654321fedcba0987654321"),
            ) as regenerate_secret,
            patch.object(
                calendar_router,
                "get_user_subscriptions",
                AsyncMock(return_value=(active_subscriptions, 1)),
            ),
            patch.object(
                calendar_router,
                "get_calendar_aggregated_schedule",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                calendar_router,
                "_get_source_update_map",
                AsyncMock(return_value={}),
            ),
        ):
            response = self.client.post("/api/cal/subscription/reset")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["http_url"],
            "https://api.example.com/api/cal/fedcba0987654321fedcba0987654321.ics",
        )
        self.assertEqual(
            payload["webcal_url"],
            "webcal://api.example.com/api/cal/fedcba0987654321fedcba0987654321.ics",
        )
        regenerate_secret.assert_awaited_once_with(54321)

    def test_reset_subscription_requires_telegram_link(self):
        self._override_user(None, preferences={})

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

    def test_toggle_subscription_persists_sync_state(self):
        account = types.SimpleNamespace(preferences={})
        self._override_user(10001, preferences={}, db_obj=account)

        with (
            patch.object(
                calendar_router,
                "_get_account_for_current_user",
                AsyncMock(return_value=account),
            ),
            patch.object(
                calendar_router,
                "get_user_subscriptions",
                AsyncMock(return_value=([], 0)),
            ),
            patch.object(
                calendar_router,
                "get_or_create_calendar_secret",
                AsyncMock(return_value="secret999"),
            ),
        ):
            response = self.client.post("/api/cal/subscription/toggle", json={"enabled": False})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["sync_enabled"])
        self.assertFalse(payload["enabled"])
        self.assertFalse(account.preferences["calendar_sync"]["enabled"])

    def test_create_custom_profile_selects_profile(self):
        account = types.SimpleNamespace(preferences={})
        self._override_user(10002, preferences={}, db_obj=account)
        aggregate_mock = AsyncMock(return_value=[])

        with (
            patch.object(
                calendar_router,
                "_get_account_for_current_user",
                AsyncMock(return_value=account),
            ),
            patch.object(
                calendar_router,
                "get_user_subscriptions",
                AsyncMock(return_value=([], 0)),
            ),
            patch.object(
                calendar_router,
                "get_or_create_calendar_secret",
                AsyncMock(return_value="secret1002"),
            ),
            patch.object(
                calendar_router,
                "get_calendar_aggregated_schedule",
                aggregate_mock,
            ),
            patch.object(
                calendar_router,
                "_get_source_update_map",
                AsyncMock(return_value={}),
            ),
        ):
            response = self.client.post(
                "/api/cal/subscription/profiles",
                json={
                    "entity_type": "group",
                    "entity_id": "group-1",
                    "entity_name": "Group 1",
                    "lesson_mode": "exams_only",
                    "modules": ["Core"],
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["selected_profile_id"].startswith("custom-"))
        custom_profile = next(
            profile
            for profile in payload["profiles"]
            if profile["id"] == payload["selected_profile_id"]
        )
        self.assertEqual(custom_profile["lesson_mode"], "exams_only")
        self.assertEqual(custom_profile["modules"], ["Core"])
        self.assertTrue(custom_profile["selected"])
        self.assertTrue(payload["enabled"])
        aggregate_mock.assert_awaited()
        aggregate_sources = aggregate_mock.await_args.args[0]
        self.assertEqual(
            aggregate_sources,
            [
                {
                    "id": payload["selected_profile_id"],
                    "entity_type": "group",
                    "entity_id": "group-1",
                    "entity_name": "Group 1",
                }
            ],
        )

    def test_public_feed_returns_cache_headers(self):
        active_subscriptions = [
            {
                "id": 99,
                "is_active": True,
                "entity_type": "group",
                "entity_id": "group-1",
                "entity_name": "Group 1",
            }
        ]
        profile = {
            "id": "all",
            "name": "All classes",
            "kind": "built_in",
            "lesson_mode": "all",
            "can_delete": False,
            "scope_label": "All active Telegram schedule subscriptions",
        }

        with (
            patch.object(
                calendar_router,
                "_resolve_public_calendar_context",
                AsyncMock(
                    return_value=(
                        12345,
                        None,
                        calendar_router._default_calendar_sync_state(),
                        active_subscriptions,
                        profile,
                    )
                ),
            ),
            patch.object(
                calendar_router,
                "get_calendar_aggregated_schedule",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                calendar_router,
                "_get_source_update_map",
                AsyncMock(return_value={}),
            ),
            patch.object(
                calendar_router,
                "generate_profile_ical_from_aggregated_schedule",
                lambda *args, **kwargs: b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n",
            ),
        ):
            response = self.client.get("/api/cal/secret123.ics")

        self.assertEqual(response.status_code, 200)
        self.assertIn("ETag", response.headers)
        self.assertEqual(response.headers["Cache-Control"], "private, max-age=0, must-revalidate")
        self.assertIn("inline; filename=", response.headers["Content-Disposition"])

    def test_public_custom_feed_uses_custom_profile_source_without_bot_subscription(self):
        sync_state = calendar_router._default_calendar_sync_state()
        custom_profile = {
            "id": "custom-web",
            "name": "Group 2",
            "kind": "custom",
            "lesson_mode": "all",
            "entity_type": "group",
            "entity_id": "group-2",
            "entity_name": "Group 2",
            "modules": [],
            "can_delete": True,
        }
        sync_state["custom_profiles"].append(custom_profile)
        aggregate_mock = AsyncMock(return_value=[])

        with (
            patch.object(
                calendar_router,
                "_resolve_public_calendar_context",
                AsyncMock(return_value=(12345, None, sync_state, [], custom_profile)),
            ),
            patch.object(
                calendar_router,
                "get_calendar_aggregated_schedule",
                aggregate_mock,
            ),
            patch.object(
                calendar_router,
                "_get_source_update_map",
                AsyncMock(return_value={}),
            ),
            patch.object(
                calendar_router,
                "generate_profile_ical_from_aggregated_schedule",
                lambda *args, **kwargs: b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n",
            ),
        ):
            response = self.client.get("/api/cal/secret123/profiles/custom-web.ics")

        self.assertEqual(response.status_code, 200)
        aggregate_mock.assert_awaited_once()
        self.assertEqual(
            aggregate_mock.await_args.args[0],
            [
                {
                    "id": "custom-web",
                    "entity_type": "group",
                    "entity_id": "group-2",
                    "entity_name": "Group 2",
                }
            ],
        )

    def test_public_builtin_feed_combines_bot_and_custom_sources(self):
        active_subscriptions = [
            {
                "id": 77,
                "is_active": True,
                "entity_type": "group",
                "entity_id": "group-1",
                "entity_name": "Group 1",
            }
        ]
        sync_state = calendar_router._default_calendar_sync_state()
        sync_state["custom_profiles"].append(
            {
                "id": "custom-web",
                "name": "Group 2",
                "kind": "custom",
                "lesson_mode": "all",
                "entity_type": "group",
                "entity_id": "group-2",
                "entity_name": "Group 2",
                "modules": [],
                "can_delete": True,
            }
        )
        profile = dict(calendar_router.BUILT_IN_PROFILES[0])
        aggregate_mock = AsyncMock(return_value=[])

        with (
            patch.object(
                calendar_router,
                "_resolve_public_calendar_context",
                AsyncMock(return_value=(12345, None, sync_state, active_subscriptions, profile)),
            ),
            patch.object(
                calendar_router,
                "get_calendar_aggregated_schedule",
                aggregate_mock,
            ),
            patch.object(
                calendar_router,
                "_get_source_update_map",
                AsyncMock(return_value={}),
            ),
            patch.object(
                calendar_router,
                "generate_profile_ical_from_aggregated_schedule",
                lambda *args, **kwargs: b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n",
            ),
        ):
            response = self.client.get("/api/cal/secret123.ics")

        self.assertEqual(response.status_code, 200)
        aggregate_mock.assert_awaited_once()
        self.assertEqual(
            aggregate_mock.await_args.args[0],
            [
                active_subscriptions[0],
                {
                    "id": "custom-web",
                    "entity_type": "group",
                    "entity_id": "group-2",
                    "entity_name": "Group 2",
                },
            ],
        )

    def test_public_telegram_filtered_feed_uses_aggregated_schedule(self):
        active_subscriptions = [
            {
                "id": 77,
                "is_active": True,
                "entity_type": "group",
                "entity_id": "group-1",
                "entity_name": "Group 1",
            }
        ]

        with (
            patch.object(
                calendar_router,
                "get_user_id_by_calendar_secret",
                AsyncMock(return_value=12345),
            ),
            patch.object(
                calendar_router,
                "get_user_subscriptions",
                AsyncMock(return_value=(active_subscriptions, 1)),
            ),
            patch.object(
                calendar_router.redis_client,
                "get_user_cache",
                AsyncMock(return_value={"excluded_subs": [], "excluded_types": []}),
            ),
            patch.object(
                calendar_router,
                "get_aggregated_schedule",
                AsyncMock(return_value=[]),
            ) as aggregated_mock,
            patch.object(
                calendar_router,
                "generate_profile_ical_from_aggregated_schedule",
                lambda *args, **kwargs: b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n",
            ),
        ):
            response = self.client.get("/api/cal/secret123/telegram.ics")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/calendar", response.headers.get("content-type", ""))
        self.assertIn(
            'inline; filename="matplobbot-telegram-filtered.ics"',
            response.headers.get("content-disposition", ""),
        )
        aggregated_mock.assert_awaited()

"""Real interval, source completeness, timezone and API validation regressions."""

import unittest
from datetime import UTC, date, datetime, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_stats_app.routers import planning_router
from shared_lib.services.schedule_planning import analyze_schedules, load_schedule_plan


def lesson(day="2026-10-09", begin="10:00", end="11:30", name="Math", **extra):
    return {
        "date": day,
        "beginLesson": begin,
        "endLesson": end,
        "discipline": name,
        "kindOfWork": "Лекция",
        "auditorium": "101",
        "lecturer_title": "Teacher",
        **extra,
    }


def source(ident, lessons, **extra):
    return {
        "entity_type": "group",
        "entity_id": ident,
        "schedule": lessons,
        "freshness": "live",
        **extra,
    }


class TestPlanningIntervals(unittest.TestCase):
    def analyze(self, sources, **kwargs):
        return analyze_schedules(
            sources, start_date=date(2026, 10, 9), end_date=date(2026, 10, 10), **kwargs
        )

    def test_conflicts_are_actual_overlaps_and_shared_lessons_are_deduplicated(self):
        common = lesson()
        result = self.analyze(
            [
                source("a", [common, lesson(begin="11:00", end="12:00", name="Physics")]),
                source("b", [common, lesson(begin="12:00", end="13:00", name="History")]),
            ]
        )
        self.assertEqual(result["lesson_count"], 3)
        self.assertEqual(len(result["conflicts"]), 1)
        conflict = result["conflicts"][0]
        self.assertTrue(conflict["start"].endswith("11:00:00+03:00"))
        self.assertTrue(conflict["end"].endswith("11:30:00+03:00"))
        self.assertEqual(conflict["lessons"][0]["sources"], ["group:a", "group:b"])
        self.assertEqual(
            [item["duration_minutes"] for item in result["free_windows"]], [120, 540, 840]
        )

    def test_different_dates_never_conflict_and_empty_verified_day_is_free(self):
        result = self.analyze([source("a", [lesson()]), source("b", [lesson(day="2026-10-10")])])
        self.assertEqual(result["conflicts"], [])
        self.assertEqual(len(result["free_windows"]), 4)
        empty = self.analyze([source("a", [])])
        self.assertEqual([item["duration_minutes"] for item in empty["free_windows"]], [840, 840])

    def test_unknown_stale_and_invalid_inputs_never_invent_free_windows(self):
        for bad_source in [
            source("a", None, freshness="unavailable"),
            source("a", [], freshness="stale_fallback"),
            source("a", [], freshness="refreshing"),
            source("a", [lesson(begin="bad")]),
        ]:
            with self.subTest(source=bad_source):
                result = self.analyze([bad_source])
                self.assertTrue(result["incomplete"])
                self.assertEqual(result["free_windows"], [])

    def test_timezone_conversion_across_midnight(self):
        result = self.analyze(
            [source("a", [lesson(day="2026-10-08", begin="23:00", end="23:50")])],
            timezone="Etc/GMT-8",
            day_start=time(3),
            day_end=time(6),
        )
        self.assertEqual(result["lesson_count"], 1)
        self.assertEqual(
            [item["duration_minutes"] for item in result["free_windows"]], [60, 70, 180]
        )
        self.assertTrue(result["free_windows"][1]["start"].startswith("2026-10-09T04:50:00+08:00"))

    def test_custom_free_window_size_and_room_caveat(self):
        result = self.analyze(
            [source("room", [lesson()], entity_type="auditorium")],
            day_start=time(9, 45),
            day_end=time(12),
            min_free_minutes=30,
        )
        self.assertEqual([item["duration_minutes"] for item in result["free_windows"]], [30, 135])
        self.assertIn("room_availability_is_timetable_only", result["warnings"])

    def test_window_limit_and_reversed_bounds(self):
        with self.assertRaises(ValueError):
            analyze_schedules(
                [source("a", [])], start_date=date(2026, 10, 1), end_date=date(2026, 10, 15)
            )
        with self.assertRaises(ValueError):
            self.analyze([source("a", [])], day_start=time(20), day_end=time(8))


class TestPlanningLoader(unittest.IsolatedAsyncioTestCase):
    async def test_profiles_share_fetch_and_union_module_filters(self):
        result = SimpleNamespace(
            schedule=[lesson(group="group"), lesson(name="Other", group="group")],
            freshness="fresh_cache",
            source_checked_at=datetime(2026, 10, 9, tzinfo=UTC),
        )
        with (
            patch(
                "shared_lib.database.get_discipline_modules_map",
                AsyncMock(return_value={"Math": "m1", "Other": "m2"}),
            ),
            patch(
                "shared_lib.services.schedule_service.get_semester_bounds",
                return_value=("2026-08-01", "2027-01-31"),
            ),
            patch(
                "shared_lib.services.schedule_freshness.get_schedule_with_freshness",
                AsyncMock(return_value=result),
            ) as load,
        ):
            plan = await load_schedule_plan(
                object(),
                [
                    {"entity_type": "group", "entity_id": "1", "selected_modules": ["m1"]},
                    {"entity_type": "group", "entity_id": "1", "selected_modules": ["m2"]},
                ],
                start_date=date(2026, 10, 9),
                end_date=date(2026, 10, 9),
            )
        self.assertEqual(plan["lesson_count"], 2)
        load.assert_awaited_once()

    async def test_outside_cached_semester_is_rejected(self):
        with patch(
            "shared_lib.services.schedule_service.get_semester_bounds",
            return_value=("2026-08-01", "2027-01-31"),
        ):
            with self.assertRaisesRegex(ValueError, "semester"):
                await load_schedule_plan(
                    object(),
                    [{"entity_type": "group", "entity_id": "1"}],
                    start_date=date(2025, 10, 9),
                    end_date=date(2025, 10, 9),
                )


class TestPlanningAPI(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(planning_router.router, prefix="/api")
        app.dependency_overrides[planning_router.get_shared_http_session] = lambda: object()
        self.client = TestClient(app)
        self.body = {
            "entities": [{"entity_type": "group", "entity_id": "1"}],
            "start_date": "2026-10-09",
            "end_date": "2026-10-10",
        }

    def test_invalid_bounds_and_entity_limits_are_rejected_before_fetch(self):
        for changes in [
            {"entities": self.body["entities"] * 7},
            {"end_date": "2026-11-10"},
            {"timezone": "arbitrary"},
            {"entities": [{"entity_type": "group", "entity_id": "../secret"}]},
        ]:
            with (
                self.subTest(changes=changes),
                patch.object(planning_router, "load_schedule_plan", AsyncMock()) as load,
            ):
                response = self.client.post("/api/schedule/plan", json={**self.body, **changes})
                self.assertEqual(response.status_code, 422)
                load.assert_not_awaited()

    def test_public_plan_uses_rate_limit_and_shared_loader(self):
        with (
            patch.object(
                planning_router,
                "load_schedule_plan",
                AsyncMock(return_value={"conflicts": [], "free_windows": [], "incomplete": False}),
            ) as load,
            patch.object(planning_router, "enforce_rate_limit", AsyncMock()) as limit,
            patch.object(planning_router, "create_ruz_api_client", return_value=object()),
        ):
            response = self.client.post("/api/schedule/plan", json=self.body)
        self.assertEqual(response.status_code, 200)
        load.assert_awaited_once()
        limit.assert_awaited_once()


class TestPlanningBot(unittest.IsolatedAsyncioTestCase):
    async def test_group_help_callback_cannot_expose_private_subscriptions(self):
        from bot.handlers.schedule_planning import SchedulePlanningManager

        manager = SchedulePlanningManager(object())
        manager.filters.get_active_subscriptions = AsyncMock()
        await manager.plan(SimpleNamespace(chat=SimpleNamespace(type="group")))
        manager.filters.get_active_subscriptions.assert_not_awaited()

    async def test_private_plan_uses_current_personal_filters_and_escapes_titles(self):
        from bot.handlers import schedule_planning as module

        manager = module.SchedulePlanningManager(object())
        manager.filters.get_active_subscriptions = AsyncMock(
            return_value=[
                {"id": 1, "entity_type": "group", "entity_id": "a"},
                {"id": 2, "entity_type": "group", "entity_id": "b"},
            ]
        )
        manager.filters.get = AsyncMock(
            return_value={"excluded_subs": [2], "excluded_types": ["Seminar"]}
        )
        status = SimpleNamespace(edit_text=AsyncMock())
        message = SimpleNamespace(
            chat=SimpleNamespace(type="private"),
            from_user=SimpleNamespace(id=42),
            answer=AsyncMock(return_value=status),
        )
        payload = {
            "conflicts": [
                {
                    "start": "2026-10-09T10:00:00+03:00",
                    "end": "2026-10-09T11:00:00+03:00",
                    "lessons": [{"discipline": "<Math>"}],
                }
            ],
            "free_windows": [],
            "incomplete": False,
            "warnings": [],
        }
        with (
            patch.object(module.translator, "get_language", AsyncMock(return_value="en")),
            patch.object(module.redis_client.client, "set", AsyncMock(return_value=True)),
            patch.object(module, "load_schedule_plan", AsyncMock(return_value=payload)) as load,
        ):
            await manager.plan(message)
        self.assertEqual([entity["entity_id"] for entity in load.await_args.args[1]], ["a"])
        self.assertEqual(load.await_args.kwargs["excluded_types"], {"Seminar"})
        self.assertIn("&lt;Math&gt;", status.edit_text.await_args.args[0])

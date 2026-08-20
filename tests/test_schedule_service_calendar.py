import hashlib
import json
import sys
import types
import unittest
from unittest.mock import AsyncMock, call, patch


class _FakeEvent:
    pass


class _FakeCalendar:
    def __init__(self):
        self.events = []

    def serialize(self):
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0"]
        for event in self.events:
            description = getattr(event, "description", "").replace("\n", "\\n")
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"SUMMARY:{getattr(event, 'name', '')}",
                    f"DESCRIPTION:{description}",
                    "END:VEVENT",
                ]
            )
        lines.append("END:VCALENDAR")
        return "\n".join(lines)


fake_ics = types.ModuleType("ics")
fake_ics.Calendar = _FakeCalendar
fake_ics.Event = _FakeEvent
sys.modules["ics"] = fake_ics

from shared_lib.services import schedule_service
from shared_lib.services.schedule_service import (
    _get_simple_lesson_type,
    generate_profile_ical_from_aggregated_schedule,
)


def _unfold_ics(payload: bytes) -> str:
    return payload.decode("utf-8").replace("\r\n ", "").replace("\r\n\t", "")


class TestScheduleServiceCalendar(unittest.TestCase):
    def test_simple_lesson_type_treats_seminar_credit_as_exam(self):
        self.assertEqual(_get_simple_lesson_type("Семинар+зачет"), "Exam")
        self.assertEqual(_get_simple_lesson_type("Экзамены"), "Exam")

    def test_simple_lesson_type_treats_pre_exam_consultation_as_consultation(self):
        self.assertEqual(_get_simple_lesson_type("Консультации перед экзаменом"), "Consultation")
        self.assertEqual(_get_simple_lesson_type("Консультации текущие"), "Consultation")

    def test_profile_ical_description_includes_source_parse_time(self):
        payload = generate_profile_ical_from_aggregated_schedule(
            [
                {
                    "date": "2026-04-07",
                    "beginLesson": "10:10",
                    "endLesson": "11:40",
                    "discipline": "Physics",
                    "kindOfWork": "Lecture",
                    "auditorium": "A-101",
                    "building": "Main",
                    "lecturer_title": "Ivanov_I_I",
                    "group": "Group 1",
                    "source_entity": "Group 1",
                    "source_entity_type": "group",
                    "source_entity_id": "group-1",
                    "source_updated_at": "2026-04-06T07:30:00+00:00",
                }
            ]
        )

        unfolded = _unfold_ics(payload)

        self.assertIn(
            "Последний парсинг расписания с сайта вуза: 10:30 06.04.2026",
            unfolded,
        )


class TestScheduleEntityIdRefresh(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_schedule_entity_id_by_name_rejects_ambiguous_non_exact_results(self):
        fake_client = types.SimpleNamespace(
            search=AsyncMock(
                return_value=[
                    {"id": "group-1", "label": "PM23-10"},
                    {"id": "group-2", "label": "PM23-11"},
                ]
            )
        )

        result = await schedule_service.resolve_schedule_entity_id_by_name(
            fake_client,
            "group",
            "PM23-1",
            "old-id",
        )

        self.assertEqual(
            result,
            {"entity_id": "old-id", "entity_name": "PM23-1", "matched": False},
        )

    async def test_refresh_failed_entity_is_reported_once(self):
        fake_client = types.SimpleNamespace(
            search=AsyncMock(
                return_value=[
                    {"id": "group-1", "label": "PM23-10"},
                    {"id": "group-2", "label": "PM23-11"},
                ]
            ),
            get_schedule=AsyncMock(),
        )

        with (
            patch.object(
                schedule_service,
                "get_cached_schedule_entities_for_id_refresh",
                AsyncMock(
                    return_value=[
                        {
                            "entity_type": "group",
                            "entity_id": "old-id",
                            "entity_name": "PM23-1",
                        }
                    ]
                ),
            ),
            patch.object(
                schedule_service,
                "get_unique_active_subscription_entities",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                schedule_service,
                "get_semester_bounds",
                return_value=("2026-08-25", "2027-01-31"),
            ),
        ):
            result = await schedule_service.refresh_cached_schedule_entity_ids_and_semester_cache(
                fake_client,
                sleep_seconds=0,
            )

        self.assertEqual(result["failed"], 1)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["status"], "failed")
        fake_client.get_schedule.assert_not_awaited()

    async def test_refresh_cached_schedule_entity_ids_remaps_and_updates_hashes(self):
        group_schedule = [{"date": "2026-09-01", "group": "PM23-1"}]
        person_schedule = [{"date": "2026-09-02", "lecturer_title": "Ivanov I.I."}]

        async def fake_search(term, entity_type):
            results = {
                ("PM23-1", "group"): [{"id": "new-group-id", "label": "PM23-1"}],
                ("Ivanov I.I.", "person"): [{"id": "person-id", "name": "Ivanov I.I."}],
            }
            return results[(term, entity_type)]

        async def fake_get_schedule(entity_type, entity_id, *, start, finish):
            self.assertEqual((start, finish), ("2026-08-25", "2027-01-31"))
            if entity_type == "group":
                self.assertEqual(entity_id, "new-group-id")
                return group_schedule
            self.assertEqual(entity_id, "person-id")
            return person_schedule

        fake_client = types.SimpleNamespace(
            search=AsyncMock(side_effect=fake_search),
            get_schedule=AsyncMock(side_effect=fake_get_schedule),
        )

        with (
            patch.object(
                schedule_service,
                "get_cached_schedule_entities_for_id_refresh",
                AsyncMock(
                    return_value=[
                        {
                            "entity_type": "group",
                            "entity_id": "old-group-id",
                            "entity_name": "PM23-1",
                        }
                    ]
                ),
            ),
            patch.object(
                schedule_service,
                "get_unique_active_subscription_entities",
                AsyncMock(
                    return_value=[
                        {
                            "entity_type": "group",
                            "entity_id": "old-group-id",
                            "entity_name": "old-group-id",
                        },
                        {
                            "entity_type": "person",
                            "entity_id": "person-id",
                            "entity_name": "Ivanov I.I.",
                        },
                    ]
                ),
            ),
            patch.object(
                schedule_service,
                "get_semester_bounds",
                return_value=("2026-08-25", "2027-01-31"),
            ),
            patch.object(schedule_service, "upsert_cached_schedule", AsyncMock()) as upsert_cache,
            patch.object(
                schedule_service,
                "reassign_schedule_entity_id_references",
                AsyncMock(
                    return_value={
                        "subscriptions_updated": 2,
                        "subscriptions_merged": 0,
                        "web_profiles_updated": 1,
                        "web_accounts_updated": 1,
                    }
                ),
            ) as reassign_refs,
            patch.object(schedule_service, "delete_cached_schedule", AsyncMock()) as delete_cache,
            patch.object(
                schedule_service, "batch_update_subscription_hashes", AsyncMock()
            ) as update_hashes,
        ):
            result = await schedule_service.refresh_cached_schedule_entity_ids_and_semester_cache(
                fake_client,
                sleep_seconds=0,
            )

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["processed"], 2)
        self.assertEqual(result["refreshed"], 2)
        self.assertEqual(result["remapped"], 1)
        self.assertEqual(result["subscriptions_updated"], 2)
        self.assertEqual(result["web_profiles_updated"], 1)
        self.assertEqual(result["items"][0]["status"], "updated")
        self.assertEqual(result["items"][1]["status"], "refreshed")

        upsert_cache.assert_has_awaits(
            [
                call("group", "new-group-id", group_schedule),
                call("person", "person-id", person_schedule),
            ]
        )
        reassign_refs.assert_awaited_once_with("group", "old-group-id", "new-group-id", "PM23-1")
        delete_cache.assert_awaited_once_with("group", "old-group-id")

        expected_group_hash = hashlib.sha256(
            json.dumps(group_schedule, sort_keys=True, default=str).encode()
        ).hexdigest()
        expected_person_hash = hashlib.sha256(
            json.dumps(person_schedule, sort_keys=True, default=str).encode()
        ).hexdigest()
        update_hashes.assert_has_awaits(
            [
                call("group", "new-group-id", expected_group_hash),
                call("person", "person-id", expected_person_hash),
            ]
        )

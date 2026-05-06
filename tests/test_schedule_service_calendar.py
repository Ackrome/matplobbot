import sys
import types
import unittest


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

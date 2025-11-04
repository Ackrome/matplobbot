# bot/services/schedule_service.py

from typing import List, Dict, Any
from datetime import datetime, date
from collections import defaultdict
from ics import Calendar, Event
from zoneinfo import ZoneInfo
from aiogram.utils.markdown import hcode

from shared_lib.i18n import translator

names_shorter = defaultdict(lambda: 'Unknown')
to_add = {
    'Практические (семинарские) занятия': 'Семинар',
    'Лекции': 'Лекция',
    'Консультации текущие': 'Консультация',
    'Повторная промежуточная аттестация (экзамен)':'Пересдача'
    }
names_shorter.update(to_add)

def _format_lesson_for_diff(lesson: Dict[str, Any], lang: str) -> str:
    """Formats a single lesson for display in a diff message."""
    date_obj = datetime.strptime(lesson['date'], "%Y-%m-%d").date()
    day_header = f"<b>{date_obj.strftime('%A, %d.%m.%Y')}</b>"
    details = [
        hcode(f"{lesson['beginLesson']} - {lesson['endLesson']} | {lesson['auditorium']}"),
        f"{lesson['discipline']} ({names_shorter[lesson['kindOfWork']]})",
        f"<i>{translator.gettext(lang, 'lecturer_prefix')}: {lesson.get('lecturer_title', 'N/A').replace('_', ' ')}</i>"
    ]
    return f"{day_header}\n" + "\n".join(details)

def diff_schedules(old_data: List[Dict[str, Any]], new_data: List[Dict[str, Any]], lang: str) -> str | None:
    """Compares two schedule datasets and returns a human-readable diff."""
    old_lessons = {lesson['lessonOid']: lesson for lesson in old_data}
    new_lessons = {lesson['lessonOid']: lesson for lesson in new_data}

    added = [lesson for oid, lesson in new_lessons.items() if oid not in old_lessons]
    removed = [lesson for oid, lesson in old_lessons.items() if oid not in new_lessons]
    modified = []

    # Fields to check for modifications
    fields_to_check = ['beginLesson', 'endLesson', 'auditorium', 'lecturer_title']

    for oid, old_lesson in old_lessons.items():
        if oid in new_lessons:
            new_lesson = new_lessons[oid]
            changes = {}
            for field in fields_to_check:
                if old_lesson.get(field) != new_lesson.get(field):
                    changes[field] = (old_lesson.get(field), new_lesson.get(field))
            if changes:
                modified.append({'new': new_lesson, 'changes': changes})

    if not added and not removed and not modified:
        return None

    diff_parts = []
    if added: diff_parts.append(f"<b>{translator.gettext(lang, 'schedule_change_added')}:</b>\n" + "\n\n".join([_format_lesson_for_diff(l, lang) for l in added]))
    if removed: diff_parts.append(f"<b>{translator.gettext(lang, 'schedule_change_removed')}:</b>\n" + "\n\n".join([_format_lesson_for_diff(l, lang) for l in removed]))
    if modified:
        modified_texts = []
        for mod in modified:
            change_descs = [f"<i>{translator.gettext(lang, f'field_{f}')}: {hcode(v[0])} → {hcode(v[1])}</i>" for f, v in mod['changes'].items()]
            modified_texts.append(f"{_format_lesson_for_diff(mod['new'], lang)}\n" + "\n".join(change_descs))
        diff_parts.append(f"<b>{translator.gettext(lang, 'schedule_change_modified')}:</b>\n" + "\n\n".join(modified_texts))

    return "\n\n---\n\n".join(diff_parts)
    

def format_schedule(schedule_data: List[Dict[str, Any]], lang: str, entity_name: str, entity_type: str, start_date: date, is_week_view: bool = False) -> str:
    """Formats a list of lessons into a readable daily schedule."""
    if not schedule_data:
        # Different message for single day vs week
        no_lessons_key = "schedule_no_lessons_week" if is_week_view else "schedule_no_lessons_day" # This was Russian text
        return translator.gettext(lang, "schedule_header_for", entity_name=entity_name) + f"\n\n{translator.gettext(lang, no_lessons_key)}"

    # Group lessons by date
    days = defaultdict(list)
    for lesson in schedule_data:
        days[lesson['date']].append(lesson)

    formatted_days = []
    # Iterate through sorted dates to build the full schedule string
    for date_str, lessons in sorted(days.items()):
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        
        day_header = f"<b>{date_obj.strftime('%A, %d.%m.%Y')}</b>"
        
        formatted_lessons = []
        for lesson in sorted(lessons, key=lambda x: x['beginLesson']):
            lesson_details = [
                hcode(f"{lesson['beginLesson']} - {lesson['endLesson']} | {lesson['auditorium']}"),
                f"{lesson['discipline']} | {names_shorter[lesson['kindOfWork']]}"
            ]

            if entity_type == 'group':
                lesson_details.append(f"{lesson['lecturer_title'].replace('_',' ')}\n{lesson.get('lecturerEmail', 'Почта не указана')}")
            elif entity_type == 'person': # Lecturer
                lesson_details.append(f" {lesson.get('group', 'Группа не указана')}")
            elif entity_type == 'auditorium':
                lesson_details.append(f"{lesson.get('group', 'Группа не указана')} | {lesson['lecturer_title'].replace('_',' ')}\n{lesson.get('lecturerEmail', 'Почта не указана')}")
            else: # Fallback to a generic format
                lesson_details.append(f"{lesson['lecturer_title'].replace('_',' ')}")

            formatted_lessons.append("\n".join(lesson_details))
        
        formatted_days.append(f"{day_header}\n" + "\n\n".join(formatted_lessons))

    main_header = translator.gettext(lang, "schedule_header_for", entity_name=entity_name)
    return f"{main_header}\n\n" + "\n\n---\n\n".join(formatted_days)

def generate_ical_from_schedule(schedule_data: List[Dict[str, Any]], entity_name: str) -> str:
    """
    Generates an iCalendar (.ics) file string from schedule data.
    """
    cal = Calendar()
    moscow_tz = ZoneInfo("Europe/Moscow")

    if not schedule_data:
        return cal.serialize()

    for lesson in schedule_data:
        try:
            event = Event()
            event.name = f"{lesson['discipline']} ({names_shorter[lesson['kindOfWork']]})"
            
            lesson_date = datetime.strptime(lesson['date'], "%Y-%m-%d").date()
            start_time = time.fromisoformat(lesson['beginLesson'])
            end_time = time.fromisoformat(lesson['endLesson'])

            event.begin = datetime.combine(lesson_date, start_time, tzinfo=moscow_tz)
            event.end = datetime.combine(lesson_date, end_time, tzinfo=moscow_tz)

            event.location = f"{lesson['auditorium']}, {lesson['building']}"
            
            description_parts = [f"Преподаватель: {lesson['lecturer_title'].replace('_',' ')}"]
            if 'group' in lesson: description_parts.append(f"Группа: {lesson['group']}")
            event.description = "\n".join(description_parts)
            
            cal.events.add(event)
        except (ValueError, KeyError) as e:
            logging.warning(f"Skipping lesson due to parsing error: {e}. Lesson data: {lesson}")
            continue
            
    return cal.serialize()
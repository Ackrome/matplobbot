# bot/services/schedule_service.py

from typing import List, Dict, Any
from datetime import datetime, date, time
from collections import defaultdict
from ics import Calendar, Event
from zoneinfo import ZoneInfo

from shared_lib.i18n import translator

names_shorter = defaultdict(lambda: 'Unknown')
to_add = {
    'Практические (семинарские) занятия': 'Семинар',
    'Лекции': 'Лекция',
    'Консультации текущие': 'Консультация',
    'Повторная промежуточная аттестация (экзамен)':'Пересдача'
    }
names_shorter.update(to_add)

    

def format_schedule(schedule_data: List[Dict[str, Any]], lang: str, entity_name: str, entity_type: str, start_date: date, is_week_view: bool = False) -> str:
    """Formats a list of lessons into a readable daily schedule."""
    if not schedule_data:
        # Different message for single day vs week
        no_lessons_key = "schedule_no_lessons_week" if is_week_view else "schedule_no_lessons_day"
        return f"🗓 *Расписание для \"{entity_name}\"*\n\n{translator.gettext(lang, no_lessons_key)}"

    # Group lessons by date
    days = defaultdict(list)
    for lesson in schedule_data:
        days[lesson['date']].append(lesson)

    formatted_days = []
    # Iterate through sorted dates to build the full schedule string
    for date_str, lessons in sorted(days.items()):
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        
        day_header = f"*{date_obj.strftime('%A, %d.%m.%Y')}*"
        
        formatted_lessons = []
        for lesson in sorted(lessons, key=lambda x: x['beginLesson']):
            lesson_details = [
                f"`{lesson['beginLesson']} - {lesson['endLesson']}`",
                f"{lesson['discipline']} | {names_shorter[lesson['kindOfWork']]}"
            ]

            if entity_type == 'group':
                lesson_details.append(f"*{lesson['auditorium']}* | {lesson['lecturer_title'].replace('_',' ')}")
            elif entity_type == 'person': # Lecturer
                lesson_details.append(f"*{lesson['auditorium']}* | {lesson.get('group', 'Группа не указана')}")
            elif entity_type == 'auditorium':
                lesson_details.append(f"{lesson.get('group', 'Группа не указана')} | {lesson['lecturer_title'].replace('_',' ')}")
            else: # Fallback to a generic format
                lesson_details.append(f"*{lesson['auditorium']}* | {lesson['lecturer_title'].replace('_',' ')}")

            formatted_lessons.append("\n".join(lesson_details))
        
        formatted_days.append(f"{day_header}\n" + "\n\n".join(formatted_lessons))

    main_header = f"🗓 *Расписание для \"{entity_name}\"*"
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
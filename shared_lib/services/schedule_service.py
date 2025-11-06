# bot/services/schedule_service.py

from typing import List, Dict, Any
from datetime import datetime, date, timedelta
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

def _format_lesson_details(lesson: Dict[str, Any], lang: str) -> str:
    """Formats the details of a single lesson into a multi-line string, without the date header."""
    details = [
        hcode(f"{lesson['beginLesson']} - {lesson['endLesson']} | {lesson['auditorium']}"),
        f"{lesson['discipline']} ({names_shorter[lesson['kindOfWork']]})",
        f"<i>{translator.gettext(lang, 'lecturer_prefix')}: {lesson.get('lecturer_title', 'N/A').replace('_', ' ')}</i>"
    ]
    return "\n".join(details)

def diff_schedules(old_data: List[Dict[str, Any]], new_data: List[Dict[str, Any]], lang: str) -> str | None:
    """Compares two schedule datasets and returns a human-readable diff."""
    if not old_data and not new_data:
        return None

    # --- FIX: Sliding Window Problem ---
    # Determine the overlapping date range to avoid flagging new days at the end of the window as "changes".
    old_dates = {datetime.strptime(d['date'], "%Y-%m-%d").date() for d in old_data}
    new_dates = {datetime.strptime(d['date'], "%Y-%m-%d").date() for d in new_data}
    
    # We only care about changes up to the last day that was present in the *old* data.
    # Any day in the new data beyond this is part of the sliding window and should be ignored.
    max_relevant_date = max(old_dates) if old_dates else (date.today() - timedelta(days=1))

    # Filter new_data to only include lessons within the relevant timeframe.
    relevant_new_data = [lesson for lesson in new_data if datetime.strptime(lesson['date'], "%Y-%m-%d").date() <= max_relevant_date]
    
    old_lessons = {lesson['lessonOid']: lesson for lesson in old_data}
    new_lessons = {lesson['lessonOid']: lesson for lesson in relevant_new_data}

    added = [lesson for oid, lesson in new_lessons.items() if oid not in old_lessons]
    removed = [lesson for oid, lesson in old_lessons.items() if oid not in new_lessons]
    modified = []

    # Fields to check for modifications
    fields_to_check = ['beginLesson', 'endLesson', 'auditorium', 'lecturer_title', 'date']

    for oid, old_lesson in old_lessons.items():
        if oid in new_lessons:
            new_lesson = new_lessons[oid]
            changes = {}
            for field in fields_to_check:
                old_val = old_lesson.get(field)
                new_val = new_lesson.get(field)
                if old_val != new_val:
                    changes[field] = (old_val, new_val)
            if changes:
                modified.append({'old': old_lesson, 'new': new_lesson, 'changes': changes})

    if not added and not removed and not modified:
        return None

    # --- NEW: Group changes by date ---
    changes_by_date = defaultdict(lambda: {'added': [], 'removed': [], 'modified': []})
    for lesson in added: changes_by_date[lesson['date']]['added'].append(lesson)
    for lesson in removed: changes_by_date[lesson['date']]['removed'].append(lesson)
    for mod in modified: changes_by_date[mod['new']['date']]['modified'].append(mod)

    # --- NEW: Build the formatted output string ---
    day_diffs = []
    for date_str, changes in sorted(changes_by_date.items()):
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        day_of_week = translator.gettext(lang, f"day_{date_obj.weekday()}")
        month_name = translator.gettext(lang, f"month_{date_obj.month-1}_gen")
        day_header = f"<b>{day_of_week}, {date_obj.day} {month_name} {date_obj.year}</b>"
        
        day_parts = [day_header]

        if changes['added']:
            for lesson in changes['added']:
                day_parts.append(f"\n✅ {translator.gettext(lang, 'schedule_change_added')}:\n{_format_lesson_details(lesson, lang)}")

        if changes['removed']:
            for lesson in changes['removed']:
                day_parts.append(f"\n❌ {translator.gettext(lang, 'schedule_change_removed')}:\n{_format_lesson_details(lesson, lang)}")

        if changes['modified']:
            for mod in changes['modified']:
                change_descs = []
                for field, (old_val, new_val) in mod['changes'].items():
                    # For date changes, format them nicely
                    if field == 'date':
                        old_date_obj = datetime.strptime(old_val, "%Y-%m-%d").date()
                        new_date_obj = datetime.strptime(new_val, "%Y-%m-%d").date()
                        old_val_str = old_date_obj.strftime('%d.%m.%Y')
                        new_val_str = new_date_obj.strftime('%d.%m.%Y')
                        change_descs.append(f"<i>{translator.gettext(lang, f'field_{field}')}: {hcode(old_val_str)} → {hcode(new_val_str)}</i>")
                    else:
                        change_descs.append(f"<i>{translator.gettext(lang, f'field_{field}')}: {hcode(old_val)} → {hcode(new_val)}</i>")
                
                modified_text = (f"\n🔄 {translator.gettext(lang, 'schedule_change_modified')}:\n"
                                 f"{_format_lesson_details(mod['new'], lang)}\n"
                                 f"{' '.join(change_descs)}")
                day_parts.append(modified_text)
        
        day_diffs.append("\n".join(day_parts))

    return "\n\n---\n\n".join(day_diffs) if day_diffs else None
    

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

        # --- LOCALIZATION FIX ---
        day_of_week = translator.gettext(lang, f"day_{date_obj.weekday()}") # e.g., day_0 for Monday
        month_name = translator.gettext(lang, f"month_{date_obj.month-1}_gen") # Genitive case for dates
        day_header = f"<b>{day_of_week}, {date_obj.day} {month_name} {date_obj.year}</b>"
        
        formatted_lessons = []
        for lesson in sorted(lessons, key=lambda x: x['beginLesson']):
            lesson_details = [
                hcode(f"{lesson['beginLesson']} - {lesson['endLesson']} | {lesson['auditorium']}"),
                f"{lesson['discipline']} | {names_shorter[lesson['kindOfWork']]}"
            ]

            if entity_type == 'group':
                lecturer_info = [lesson['lecturer_title'].replace('_',' ')]
                if lesson.get('lecturerEmail'):
                    lecturer_info.append(lesson['lecturerEmail'])
                lesson_details.append("\n".join(lecturer_info))
            elif entity_type == 'person': # Lecturer
                lesson_details.append(f" {lesson.get('group', 'Группа не указана')}")
            elif entity_type == 'auditorium':
                lecturer_info = [f"{lesson.get('group', 'Группа не указана')} | {lesson['lecturer_title'].replace('_',' ')}"]
                if lesson.get('lecturerEmail'):
                    lecturer_info.append(lesson['lecturerEmail'])
                lesson_details.append("\n".join(lecturer_info))
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
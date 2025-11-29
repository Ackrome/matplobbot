# bot/services/schedule_service.py

import logging
from typing import List, Dict, Any
from datetime import datetime, date, time, timedelta
from collections import defaultdict
from ics import Calendar, Event
from zoneinfo import ZoneInfo
from aiogram.utils.markdown import hcode
from cachetools import TTLCache

from shared_lib.i18n import translator
from shared_lib.database import get_user_settings, get_all_short_names, get_disabled_short_names_for_user, get_all_short_names_with_ids

# Cache for short names to avoid frequent DB calls
short_name_cache = TTLCache(maxsize=1, ttl=300) # Cache for 5 minutes

# --- Configuration for Lesson Styles ---
LESSON_STYLES = {
    'Практические (семинарские) занятия': ('🟨', 'Семинар'),
    'Лекции': ('🟩', 'Лекция'),
    'Консультации текущие': ('🟪', 'Консультация'),
    'Повторная промежуточная аттестация (экзамен)': ('🟥', 'Экзамен')
}

def _get_lesson_visuals(kind: str) -> tuple[str, str]:
    return LESSON_STYLES.get(kind, ('🟦', kind))

def _get_discipline_name(full_name: str, use_short_names: bool, short_names_map: dict) -> str:
    if not use_short_names:
        return full_name
    return short_names_map.get(full_name, full_name)

def _add_date_obj(lessons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for lesson in lessons:
        lesson['date_obj'] = datetime.strptime(lesson['date'], "%Y-%m-%d").date()
    return lessons

def _format_lesson_details_sync(lesson: Dict[str, Any], lang: str, use_short_names: bool, short_names_map: dict, show_emojis: bool = True) -> str:
    """Standard formatting for Diff view (single lesson)."""
    emoji, type_name = _get_lesson_visuals(lesson['kindOfWork'])
    discipline = _get_discipline_name(lesson['discipline'], use_short_names, short_names_map)
    prefix = f"{emoji} " if show_emojis else ""
    
    details = [
        hcode(f"{lesson['beginLesson']} - {lesson['endLesson']} | {lesson['auditorium']}"),
        f"{prefix}{discipline} | {type_name}",
        f"<i>{translator.gettext(lang, 'lecturer_prefix')}: {lesson.get('lecturer_title', 'N/A').replace('_', ' ')}</i>"
    ]
    return "\n".join(details)

async def format_schedule(schedule_data: List[Dict[str, Any]], lang: str, entity_name: str, entity_type: str, user_id: int, start_date: date, is_week_view: bool = False) -> str:
    """Formats a list of lessons into a readable daily schedule using Variant B (Subgroup Hierarchy)."""
    if not schedule_data:
        no_lessons_key = "schedule_no_lessons_week" if is_week_view else "schedule_no_lessons_day"
        return translator.gettext(lang, "schedule_header_for", entity_name=entity_name) + f"\n\n{translator.gettext(lang, no_lessons_key)}"

    # --- 1. Fetch Settings ---
    user_settings = await get_user_settings(user_id)
    use_short_names = user_settings.get('use_short_names', True)
    show_emojis = user_settings.get('show_schedule_emojis', True)
    show_emails = user_settings.get('show_lecturer_emails', True)
    
    short_names_map = {}
    if use_short_names:
        all_short_names_with_ids = await get_all_short_names_with_ids(page_size=1000)
        disabled_ids = await get_disabled_short_names_for_user(user_id)
        for item in all_short_names_with_ids[0]:
            if item['id'] not in disabled_ids:
                short_names_map[item['full_name']] = item['short_name']

    # --- 2. Group by Date ---
    days = defaultdict(list)
    for lesson in schedule_data:
        days[lesson['date']].append(lesson)

    formatted_days = []

    # --- 3. Process Each Day ---
    for date_str, daily_lessons in sorted(days.items()):
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        day_of_week = translator.gettext(lang, f"day_{date_obj.weekday()}")
        month_name = translator.gettext(lang, f"month_{date_obj.month-1}_gen")
        day_header = f"<b>{day_of_week}, {date_obj.day} {month_name} {date_obj.year}</b>"
        
        # --- 4. Group by Time Slot ---
        time_slots = defaultdict(list)
        for lesson in daily_lessons:
            time_key = (lesson['beginLesson'], lesson['endLesson'])
            time_slots[time_key].append(lesson)

        day_content_lines = []

        # --- 5. Process Each Time Slot (Variant B Logic) ---
        for (start_time, end_time), slot_lessons in sorted(time_slots.items()):
            
            # Group identical subjects within this time slot
            # Key: (Discipline Name, Lesson Type)
            # Value: List of lessons (differing by room/teacher)
            subject_groups = defaultdict(list)
            for lesson in slot_lessons:
                d_name = _get_discipline_name(lesson['discipline'], use_short_names, short_names_map)
                _, type_name = _get_lesson_visuals(lesson['kindOfWork'])
                key = (d_name, type_name)
                subject_groups[key].append(lesson)

            # Render the groups
            for (d_name, type_name), group_lessons in subject_groups.items():
                emoji, _ = _get_lesson_visuals(group_lessons[0]['kindOfWork'])
                emoji_prefix = f"{emoji} " if show_emojis else ""

                # --- CASE 1: Single Lesson (Standard View) ---
                if len(group_lessons) == 1:
                    l = group_lessons[0]
                    # Format: Time | Room \n Name | Type \n Teacher
                    header_line = hcode(f"{start_time} - {end_time} | {l['auditorium']}")
                    body_line = f"{emoji_prefix}{d_name} | {type_name}"
                    
                    # Teacher / Group info logic
                    extra_info = l['lecturer_title'].replace('_', ' ')
                    if entity_type == 'group' and l.get('lecturerEmail'):
                        pass # Keep concise
                    if show_emails and l.get('lecturerEmail'):
                        extra_info += f" ({l['lecturerEmail']})"
                    elif entity_type == 'person':
                        extra_info = f"{l.get('group', '???')} | {extra_info}"
                    elif entity_type == 'auditorium':
                        extra_info = f"{l.get('group', '???')} | {extra_info}"

                    block = f"{header_line}\n{body_line}\n{extra_info}"
                    day_content_lines.append(block)

                # --- CASE 2: Merged Lessons (Variant B) ---
                else:
                    # Format: 
                    # Time
                    # Emoji Name | Type
                    #   ├─ Room | Teacher
                    #   └─ Room | Teacher
                    
                    header_line = hcode(f"{start_time} - {end_time}")
                    title_line = f"{emoji_prefix}{d_name} | {type_name}"
                    
                    sub_lines = []
                    # Deduplicate exact matches (e.g. if API sends duplicates)
                    unique_sub_lessons = { (l['auditorium'], l['lecturer_title'], l.get('group','')): l for l in group_lessons }.values()
                    sorted_subs = sorted(unique_sub_lessons, key=lambda x: x['auditorium'])
                    
                    for i, l in enumerate(sorted_subs):
                        is_last = (i == len(sorted_subs) - 1)
                        tree_char = "└─" if is_last else "├─"
                        
                        room = l['auditorium']
                        who = l['lecturer_title'].replace('_', ' ')
                        
                        if show_emails and l.get('lecturerEmail'):
                            who += f" ({l['lecturerEmail']})"
                        # Adjust "who" based on context
                        if entity_type == 'person': who = l.get('group', '???')
                        
                        sub_lines.append(f"  {tree_char} {room} | {who}")

                    block = f"{header_line}\n{title_line}\n" + "\n".join(sub_lines)
                    day_content_lines.append(block)

        formatted_days.append(f"{day_header}\n" + "\n\n".join(day_content_lines))

    main_header = translator.gettext(lang, "schedule_header_for", entity_name=entity_name)
    return f"{main_header}\n\n" + "\n\n---\n\n".join(formatted_days)

def diff_schedules(old_data: List[Dict[str, Any]], new_data: List[Dict[str, Any]], lang: str, use_short_names: bool, short_names_map: dict) -> str | None:
    """Compares two schedule datasets and returns a human-readable diff."""
    if not old_data and not new_data:
        return None

    old_data = _add_date_obj(old_data)
    new_data = _add_date_obj(new_data)
    today = datetime.now(ZoneInfo("Europe/Moscow")).date()

    if old_data:
        old_dates = {d['date_obj'] for d in old_data}
        min_relevant_date, max_relevant_date = min(old_dates), max(old_dates)
    else:
        min_relevant_date, max_relevant_date = date.min, date.max

    old_lessons = {l['lessonOid']: l for l in old_data if min_relevant_date <= l['date_obj'] <= max_relevant_date and l['date_obj'] >= today}
    new_lessons = {l['lessonOid']: l for l in new_data if min_relevant_date <= l['date_obj'] <= max_relevant_date and l['date_obj'] >= today}

    all_oids = old_lessons.keys() | new_lessons.keys()
    changes_by_date = defaultdict(lambda: {'added': [], 'removed': [], 'modified': []})
    fields_to_check = ['beginLesson', 'endLesson', 'auditorium', 'lecturer_title', 'date']
    
    for oid in all_oids:
        old_lesson = old_lessons.get(oid)
        new_lesson = new_lessons.get(oid)

        if old_lesson and not new_lesson:
            changes_by_date[old_lesson['date']]['removed'].append(old_lesson)
        elif new_lesson and not old_lesson:
            changes_by_date[new_lesson['date']]['added'].append(new_lesson)
        elif old_lesson and new_lesson:
            modifications = {}
            for field in fields_to_check:
                if old_lesson.get(field) != new_lesson.get(field):
                    modifications[field] = (old_lesson.get(field), new_lesson.get(field))
            if modifications:
                changes_by_date[new_lesson['date']]['modified'].append({'old': old_lesson, 'new': new_lesson, 'changes': modifications})

    if not changes_by_date:
        return None

    day_diffs = []
    for date_str, changes in sorted(changes_by_date.items()):
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        day_of_week = translator.gettext(lang, f"day_{date_obj.weekday()}")
        month_name = translator.gettext(lang, f"month_{date_obj.month-1}_gen")
        day_header = f"<b>{day_of_week}, {date_obj.day} {month_name} {date_obj.year}</b>"

        day_parts = [day_header]

        if changes['added']:
            for lesson in changes['added']:
                # Revert to default behavior for Diff view as grouping here is too complex and less readable for diffs
                day_parts.append(f"\n✅ {translator.gettext(lang, 'schedule_change_added')}:\n{_format_lesson_details_sync(lesson, lang, use_short_names, short_names_map)}")

        if changes['removed']:
            for lesson in changes['removed']:
                day_parts.append(f"\n❌ {translator.gettext(lang, 'schedule_change_removed')}:\n{_format_lesson_details_sync(lesson, lang, use_short_names, short_names_map)}")

        if changes['modified']:
            for mod in changes['modified']:
                change_descs = []
                for field, (old_val, new_val) in mod['changes'].items():
                    if field == 'date':
                        old_date_obj = datetime.strptime(old_val, "%Y-%m-%d").date()
                        new_date_obj = datetime.strptime(new_val, "%Y-%m-%d").date()
                        change_descs.append(f"<i>{translator.gettext(lang, f'field_{field}')}: {hcode(old_date_obj.strftime('%d.%m.%Y'))} → {hcode(new_date_obj.strftime('%d.%m.%Y'))}</i>")
                    else:
                        change_descs.append(f"<i>{translator.gettext(lang, f'field_{field}')}: {hcode(old_val)} → {hcode(new_val)}</i>")

                modified_text = (f"\n🔄 {translator.gettext(lang, 'schedule_change_modified')}:\n"
                                 f"{_format_lesson_details_sync(mod['new'], lang, use_short_names, short_names_map)}\n"
                                 f"{' '.join(change_descs)}")
                day_parts.append(modified_text)
        
        day_diffs.append("\n".join(day_parts))

    return "\n\n---\n\n".join(day_diffs) if day_diffs else None

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
            emoji, type_name = _get_lesson_visuals(lesson['kindOfWork'])
            event.name = f"{emoji} {lesson['discipline']} ({type_name})"
            
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
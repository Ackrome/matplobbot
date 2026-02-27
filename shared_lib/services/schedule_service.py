# shared_lib/services/schedule_service.py
import logging
from typing import List, Dict, Any
from datetime import datetime, date, time, timedelta
from collections import defaultdict
from ics import Calendar, Event
from zoneinfo import ZoneInfo
from aiogram.utils.markdown import hcode
from cachetools import TTLCache
from datetime import date
import re


from shared_lib.i18n import translator
from shared_lib.database import get_user_settings, get_all_short_names, get_disabled_short_names_for_user, get_all_short_names_with_ids, get_discipline_modules_map, get_subscription_modules

# Cache for short names to avoid frequent DB calls
short_name_cache = TTLCache(maxsize=1, ttl=300) # Cache for 5 minutes

# --- Configuration for Lesson Styles ---
LESSON_STYLES = {
    'Практические (семинарские) занятия': ('🟨', 'Семинар'),
    'Лекции': ('🟩', 'Лекция'),
    'Консультации текущие': ('🟪', 'Консультация'),
    'Повторная промежуточная аттестация (экзамен)': ('🟥', 'Экзамен')
}

MODULE_REGEX = re.compile(r'Модуль\s+["«](.+?)["»]')


def get_module_name(group_name: str | None) -> str | None:
    if not group_name: return None
    match = MODULE_REGEX.search(group_name)
    return match.group(1).strip() if match else None


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

async def format_schedule(
    schedule_data: List[Dict[str, Any]],
    lang: str,
    entity_name: str,
    entity_type: str,
    user_id: int,
    start_date: date,
    is_week_view: bool = False,
    subscription_id: int = None) -> str:
    """Formats a list of lessons into a readable daily schedule using Variant B (Subgroup Hierarchy)."""
    if not schedule_data:
        no_lessons_key = "schedule_no_lessons_week" if is_week_view else "schedule_no_lessons_day"
        return translator.gettext(lang, "schedule_header_for", entity_name=entity_name) + f"\n\n{translator.gettext(lang, no_lessons_key)}"
    
    # --- 0. Filtering Logic (NEW) ---
    if subscription_id and entity_type == 'group':
        # 1. Загружаем настройки пользователя (какие модули он хочет видеть)
        selected_modules = await get_subscription_modules(subscription_id)
        
        # Если список selected_modules пуст, считаем, что пользователь 
        # еще не настроил фильтры -> показываем всё (или ничего, зависит от политики).
        # Обычно, если список пуст в БД, это значит "фильтрация выключена". 
        # Но если мы хотим строгую фильтрацию: "не выбрал - не увидел".
        # Давайте сделаем так: если selected_modules не None, фильтруем.
        
        if selected_modules is not None: 
            # 2. Загружаем маппинг от админа
            discipline_to_module = await get_discipline_modules_map()
            
            filtered_data = []
            for lesson in schedule_data:
                # Определяем, относится ли урок к модулю (Явно или через Маппинг)
                group_val = lesson.get('group')
                explicit_mod = get_module_name(group_val) if isinstance(group_val, str) else None
                
                disc_name = lesson.get('discipline', '')
                mapped_mod = discipline_to_module.get(disc_name)
                
                # Логика:
                # Это модуль, если найден explicit_mod ИЛИ mapped_mod.
                is_module_lesson = (explicit_mod is not None) or (mapped_mod is not None)
                
                if not is_module_lesson:
                    # Это общая дисциплина -> ПОКАЗЫВАЕМ
                    filtered_data.append(lesson)
                    continue
                
                # Если это модуль, проверяем, выбран ли он пользователем
                is_selected = False
                if explicit_mod and explicit_mod in selected_modules: is_selected = True
                if mapped_mod and mapped_mod in selected_modules: is_selected = True
                
                if is_selected:
                    filtered_data.append(lesson)
            
            schedule_data = filtered_data
                    
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

def generate_ical_from_aggregated_schedule(schedule_data: List[Dict[str, Any]]) -> str:
    """
    Генерирует iCal файл для агрегированного расписания (/myschedule).
    Отличается тем, что добавляет источник (source_entity) в заголовок события.
    """
    cal = Calendar()
    moscow_tz = ZoneInfo("Europe/Moscow")

    if not schedule_data:
        return cal.serialize()

    for lesson in schedule_data:
        try:
            event = Event()
            emoji, type_name = _get_lesson_visuals(lesson['kindOfWork'])
            
            # Добавляем источник (например, название группы) в название события
            source = lesson.get('source_entity', '')
            source_prefix = f"[{source}] " if source else ""
            
            event.name = f"{source_prefix}{emoji} {lesson['discipline']} ({type_name})"
            
            lesson_date = datetime.strptime(lesson['date'], "%Y-%m-%d").date()
            start_time = time.fromisoformat(lesson['beginLesson'])
            end_time = time.fromisoformat(lesson['endLesson'])

            event.begin = datetime.combine(lesson_date, start_time, tzinfo=moscow_tz)
            event.end = datetime.combine(lesson_date, end_time, tzinfo=moscow_tz)

            event.location = f"{lesson['auditorium']}, {lesson['building']}"
            
            description_parts = []
            if source:
                description_parts.append(f"Источник: {source}")
            description_parts.append(f"Преподаватель: {lesson.get('lecturer_title', '').replace('_',' ')}")
            
            if 'group' in lesson: 
                description_parts.append(f"Группы: {lesson['group']}")
                
            event.description = "\n".join(description_parts)
            
            cal.events.add(event)
        except (ValueError, KeyError) as e:
            logging.warning(f"Skipping aggregated lesson due to parsing error: {e}")
            continue
            
    return cal.serialize()

def get_semester_bounds() -> tuple[str, str]:
    """
    Возвращает даты начала и конца текущего/предстоящего семестра
    в формате ('YYYY.MM.DD', 'YYYY.MM.DD').
    """
    today = date.today()
    year = today.year

    # Весенний семестр (Февраль - Июль)
    if 1 < today.month < 7:
        start_date = date(year, 2, 1)
        end_date = date(year, 7, 15)
    # Летние каникулы (переход к осеннему)
    elif today.month == 7 and today.day >= 15:
        start_date = date(year, 8, 25)
        end_date = date(year + 1, 1, 31)
    # Осенний семестр (Сентябрь - Январь)
    elif today.month >= 8:
        start_date = date(year, 8, 25)
        end_date = date(year + 1, 1, 31)
    # Январь (конец осеннего)
    else: # today.month == 1
        start_date = date(year - 1, 8, 25)
        end_date = date(year, 1, 31)

    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")

async def get_unique_modules_hybrid(schedule_data: list[dict]) -> list[str]:
    """
    Возвращает список доступных модулей, учитывая и Regex из group, 
    и ручные маппинги (дисциплина -> модуль) из БД.
    """
    modules = set()
    
    # 1. Получаем маппинг от админа
    discipline_to_module = await get_discipline_modules_map()
    
    for lesson in schedule_data:
        # А. Проверяем явный модуль в названии группы
        group = lesson.get('group')
        if isinstance(group, str):
            name = get_module_name(group)
            if name:
                modules.add(name)
        
        # Б. Проверяем маппинг по названию дисциплины
        disc = lesson.get('discipline')
        if disc and disc in discipline_to_module:
            modules.add(discipline_to_module[disc])
            
    return sorted(list(modules))


async def get_aggregated_schedule(
    user_id: int,
    subscriptions: list[dict],
    start_date: date,
    end_date: date,
    filter_config: dict = None
) -> list[dict]:
    """
    Собирает расписание со всех подписок, применяет фильтры и возвращает плоский список пар.
    filter_config: {
        'excluded_subs': [sub_id, ...],
        'excluded_types': ['Лекции', 'Seminars', ...],
        # Модули фильтруются на основе настроек каждой подписки в БД
    }
    """
    if not filter_config:
        filter_config = {}

    aggregated_lessons = []
    
    # 1. Загружаем глобальный маппинг дисциплин (для гибридной фильтрации модулей)
    discipline_to_module = await get_discipline_modules_map()

    from shared_lib.database import get_cached_schedule # Импорт внутри во избежание циклов

    for sub in subscriptions:
        # --- Фильтр по Источнику ---
        if sub['id'] in filter_config.get('excluded_subs', []):
            continue

        # Получаем кэш
        cached_data = await get_cached_schedule(sub['entity_type'], sub['entity_id'])
        if not cached_data:
            continue

        # Получаем настройки модулей для ЭТОЙ подписки
        selected_modules = await get_subscription_modules(sub['id'])

        for lesson in cached_data:
            # Проверка даты
            try:
                l_date = datetime.strptime(lesson['date'], "%Y-%m-%d").date()
                if not (start_date <= l_date <= end_date):
                    continue
            except ValueError:
                continue

            # --- Фильтр по Типу занятия ---
            # Упрощаем типы для фильтрации: 'Lecture', 'Seminar', 'Exam', 'Other'
            kind = lesson.get('kindOfWork', '')
            simple_type = 'Other'
            if 'Лекци' in kind: simple_type = 'Lecture'
            elif 'Практич' in kind or 'Семинар' in kind or 'Лаборат' in kind: simple_type = 'Seminar'
            elif 'экзамен' in kind.lower() or 'аттестация' in kind.lower() or 'зачет' in kind.lower(): simple_type = 'Exam'

            if simple_type in filter_config.get('excluded_types', []):
                continue

            # --- Фильтр по Модулям (Гибридный) ---
            if sub['entity_type'] == 'group' and selected_modules:
                # (Копируем логику из format_schedule)
                group_val = lesson.get('group')
                explicit_module = get_module_name(group_val) if isinstance(group_val, str) else None
                discipline_name = lesson.get('discipline', '')
                mapped_module = discipline_to_module.get(discipline_name)

                # Если это модуль, и он НЕ выбран -> пропускаем
                is_module = (explicit_module is not None) or (mapped_module is not None)
                is_selected = False
                if explicit_module and explicit_module in selected_modules: is_selected = True
                if mapped_module and mapped_module in selected_modules: is_selected = True
                
                if is_module and not is_selected:
                    continue

            # Добавляем метку источника, чтобы в общем списке понимать, чья пара
            lesson_copy = lesson.copy()
            lesson_copy['source_entity'] = sub['entity_name']
            aggregated_lessons.append(lesson_copy)

    # Сортируем по времени
    aggregated_lessons.sort(key=lambda x: (x['date'], x['beginLesson']))
    return aggregated_lessons
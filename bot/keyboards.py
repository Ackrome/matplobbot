import logging
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta, date
from aiogram.utils.keyboard import InlineKeyboardBuilder
from cachetools import LRUCache
import hashlib
import matplobblib
import os # Import os to access environment variables like ADMIN_USER_IDS
from typing import List, Dict, Any
from . import database # Import database to check for user repos
from .config import ADMIN_USER_IDS
from shared_lib.i18n import translator
import calendar


logger = logging.getLogger(__name__)

# Define base commands that are always available
BASE_COMMANDS = ['/schedule', '/myschedule', '/matp_all', '/matp_search', '/lec_search', '/lec_all', '/favorites', '/settings', '/help', '/latex', '/mermaid', '🌐 Language / Язык']
ADMIN_COMMANDS = ['/update', '/clear_cache']

# Cache for long code paths to use in callback_data
code_path_cache = LRUCache(maxsize=1024)

# Pre-generate data structure for topics and codes, not actual ReplyKeyboards.
# This structure will be used by functions to build keyboards dynamically.
# topics_data = {submodule_name: {'topics': [list_of_topics], 'codes': {topic_name: [list_of_codes]}}}
topics_data = dict()

logger.info("Начало генерации данных для клавиатур тем и задач.")
for submodule_name in matplobblib.submodules:
    logger.debug(f"Обработка подмодуля: {submodule_name} для topics_data.")
    try:
        module = matplobblib._importlib.import_module(f'matplobblib.{submodule_name}')
        # We need to get keys from themes_list_dicts_full for topics and codes
        # regardless of show_docstring, as the keyboard structure should be consistent.
        # The content (code with/without docstring) is handled in handlers.py.
        module_full_dict = module.themes_list_dicts_full # Assuming this always exists and has all keys
        module_topics = list(module_full_dict.keys())
        logger.debug(f"Темы для {submodule_name}: {module_topics}")

        sub_topics_codes = {
            topic_key: list(module_full_dict[topic_key].keys())
            for topic_key in module_topics
        }
        topics_data[submodule_name] = {
            'topics': module_topics,
            'codes': sub_topics_codes
        }
        logger.debug(f"Успешно сгенерированы данные для подмодуля: {submodule_name}")
    except NameError as e: # <-- Ловим конкретно эту ошибку
        logger.error(f"КРИТИЧЕСКАЯ ОШИБКА в библиотеке matplobblib, подмодуль '{submodule_name}' не будет загружен: {e}")
        continue
    except KeyError as e:
        logger.error(f"КРИТИЧЕСКАЯ ОШИБКА в библиотеке matplobblib, подмодуль '{submodule_name}' не будет загружен: {e}")
        continue
    except Exception as e:
        logger.error(f"Ошибка генерации данных для подмодуля {submodule_name}: {e}", exc_info=True)

logger.info("Завершение генерации данных для клавиатур тем и задач.")

def _get_user_commands(user_id: int) -> list[str]:
    """Helper to get commands for a user."""
    commands = list(BASE_COMMANDS)
    if user_id in ADMIN_USER_IDS:
        commands.extend(ADMIN_COMMANDS)
    return commands

# Function to get the main ReplyKeyboardMarkup (used for /start, after /code)
async def get_main_reply_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    current_commands = _get_user_commands(user_id)
    keyboard_buttons = [[KeyboardButton(text=cmd)] for cmd in current_commands]
    lang = await translator.get_language(user_id)
    return ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True,
        input_field_placeholder=translator.gettext(lang, 'main_menu_placeholder'),
        one_time_keyboard=True,
    )






# Function to get the help InlineKeyboardMarkup
async def get_help_inline_keyboard(user_id: int) -> InlineKeyboardMarkup:
    lang = await translator.get_language(user_id)

    inline_keyboard_rows = [
        [InlineKeyboardButton(text=translator.gettext(lang, "help_btn_matp_all"), callback_data="help_cmd_matp_all")],
        [InlineKeyboardButton(text=translator.gettext(lang, "help_btn_matp_search"), callback_data="help_cmd_matp_search")],
        [InlineKeyboardButton(text=translator.gettext(lang, "help_btn_schedule"), callback_data="help_cmd_schedule")],
        [InlineKeyboardButton(text=translator.gettext(lang, "help_btn_myschedule"), callback_data="help_cmd_myschedule")],
        [InlineKeyboardButton(text=translator.gettext(lang, "help_btn_lec_search"), callback_data="help_cmd_lec_search")],
        [InlineKeyboardButton(text=translator.gettext(lang, "help_btn_lec_all"), callback_data="help_cmd_lec_all")],
        [InlineKeyboardButton(text=translator.gettext(lang, "help_btn_favorites"), callback_data="help_cmd_favorites")],
        [InlineKeyboardButton(text=translator.gettext(lang, "help_btn_settings"), callback_data="help_cmd_settings")],
        [InlineKeyboardButton(text=translator.gettext(lang, "help_btn_latex"), callback_data="help_cmd_latex")],
        [InlineKeyboardButton(text=translator.gettext(lang, "help_btn_mermaid"), callback_data="help_cmd_mermaid")], # <--- ДОБАВЛЕНА ЗАПЯТАЯ
        [InlineKeyboardButton(text=translator.gettext(lang, "help_btn_offershorter"), callback_data="help_cmd_offershorter")]
    ]
    if user_id in ADMIN_USER_IDS:
        inline_keyboard_rows.append([InlineKeyboardButton(text=translator.gettext(lang, "help_btn_update"), callback_data="help_cmd_update")])
        inline_keyboard_rows.append([InlineKeyboardButton(text=translator.gettext(lang, "help_btn_clear_cache"), callback_data="help_cmd_clear_cache")])
    
    inline_keyboard_rows.append([InlineKeyboardButton(text=translator.gettext(lang, "help_btn_help"), callback_data="help_cmd_help")])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard_rows)

def get_code_action_keyboard(code_path: str) -> InlineKeyboardMarkup:
    """
    Создает инлайн-клавиатуру для действий с кодом.
    :param code_path: Уникальный путь к коду, например "pyplot.line_plot.simple_plot"
    """
    # Используем хэш для длинных путей, чтобы избежать ошибки Telegram "BUTTON_DATA_INVALID"
    path_hash = hashlib.sha1(code_path.encode()).hexdigest()[:16]
    code_path_cache[path_hash] = code_path

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="▶️ Выполнить", callback_data=f"run_hash:{path_hash}"),
        InlineKeyboardButton(text="⭐ В избранное", callback_data=f"fav_hash:{path_hash}")
    )
    return builder.as_markup()

async def get_repo_management_keyboard(user_id: int, state: FSMContext | None = None, chat_id: int | None = None) -> InlineKeyboardMarkup:
    """Creates an inline keyboard for managing user repositories."""
    lang = await translator.get_language(user_id, chat_id)
    repos = await database.get_user_repos(user_id)
    builder = InlineKeyboardBuilder()
    current_state_str = await state.get_state() if state else None

    for repo_path in repos:
        repo_hash = hashlib.sha1(repo_path.encode()).hexdigest()[:16]
        code_path_cache[repo_hash] = repo_path
        builder.row(
            InlineKeyboardButton(text=f"📂 {repo_path}", callback_data="noop"),
            InlineKeyboardButton(text="✏️", callback_data=f"repo_edit_hash:{repo_hash}"),
            InlineKeyboardButton(text="🔄", callback_data=f"repo_index_hash:{repo_hash}"),
            InlineKeyboardButton(text=translator.gettext(lang, "favorites_remove_btn"), callback_data=f"repo_del_hash:{repo_hash}")
        )
    builder.row(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_add_repo"), callback_data="repo_add_new"))
    
    # Conditionally add the correct "back" button
    if current_state_str == "onboarding:github":
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_back_to_tour"), callback_data="onboarding_next"))
    else:
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "back_to_settings"), callback_data="back_to_settings"))
    return builder.as_markup()



async def get_schedule_type_keyboard(lang: str, history_items: list = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator.gettext(lang, "schedule_btn_group"),
            callback_data="sch_type_group"
        ),
        InlineKeyboardButton(
            text=translator.gettext(lang, "schedule_btn_teacher"),
            callback_data="sch_type_person"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator.gettext(lang, "schedule_btn_auditorium"),
            callback_data="sch_type_auditorium"
        )
    )

    # --- NEW: Add history buttons if they exist ---
    if history_items:
        builder.row(InlineKeyboardButton(text="---", callback_data="noop")) # Separator
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "schedule_previous_searches"), callback_data="noop"))
        for item in history_items:
            builder.row(InlineKeyboardButton(
                text=f"🔎 {item['entity_name']}",
                callback_data=f"sch_history:{item['entity_type']}:{item['entity_id']}"
            ))
        builder.row(InlineKeyboardButton(
            text=translator.gettext(lang, "schedule_clear_history_btn"),
            callback_data="sch_clear_history"
        ))

    return builder.as_markup()

def build_search_results_keyboard(results: List[Dict[str, Any]], search_type: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    # Special handling for the subscribe button which has a different data structure
    # We hash the long data to avoid hitting the 64-byte callback_data limit.
    if search_type == 'subscribe':
        item = results[0]
        data_to_hash = item['id'] # e.g., "person:uuid:Name"
        data_hash = hashlib.sha1(data_to_hash.encode()).hexdigest()[:16]
        code_path_cache[data_hash] = data_to_hash # Store the full data in the cache
        builder.row(InlineKeyboardButton(text=item['label'], callback_data=f"sch_subscribe_hash:{data_hash}"))
        return builder.as_markup()

    for item in results[:20]: # Limit to 20 results to avoid hitting Telegram limits
        builder.row(
            InlineKeyboardButton(
                text=item['label'], 
                callback_data=f"sch_result_:{item.get('type', search_type)}:{item['id']}"
            )
        )
    return builder.as_markup()

def build_calendar_keyboard(year: int, month: int, entity_type: str, entity_id: str, lang: str, selected_date: date | None = None) -> InlineKeyboardMarkup:
    """Builds an inline calendar keyboard for a given month and year."""
    builder = InlineKeyboardBuilder()

    # Month and year navigation
    month_names = translator.gettext(lang, "calendar_months").split(',')
    month_name = month_names[month - 1]
    builder.row(
        InlineKeyboardButton(text="«", callback_data=f"cal_nav:prev_year:{year}:{month}:{entity_type}:{entity_id}"),
        InlineKeyboardButton(text="<", callback_data=f"cal_nav:prev_month:{year}:{month}:{entity_type}:{entity_id}"),
        InlineKeyboardButton(text=f"{month_name} {year}", callback_data="noop"),
        InlineKeyboardButton(text=">", callback_data=f"cal_nav:next_month:{year}:{month}:{entity_type}:{entity_id}"),
        InlineKeyboardButton(text="»", callback_data=f"cal_nav:next_year:{year}:{month}:{entity_type}:{entity_id}")
    )

    # Days of the week header
    day_names = translator.gettext(lang, "calendar_days_short").split(',')
    builder.row(*[InlineKeyboardButton(text=day, callback_data="noop") for day in day_names])

    # Calendar days
    month_calendar = calendar.monthcalendar(year, month)
    today = datetime.now().date()

    for week in month_calendar:
        week_buttons = []
        for day in week:
            if day == 0:
                week_buttons.append(InlineKeyboardButton(text=" ", callback_data="noop"))
            else:
                current_date = datetime(year, month, day).date()
                date_str = current_date.strftime("%Y-%m-%d")
                label = str(day)
                
                # Highlight the selected date, with priority over today's date
                if selected_date and current_date == selected_date:
                    label = f"*{label}*"
                elif current_date == today:
                    label = f"[{label}]"
                
                callback_data = f"sch_date_:{entity_type}:{entity_id}:{date_str}"
                week_buttons.append(InlineKeyboardButton(text=label, callback_data=callback_data))
        builder.row(*week_buttons)

    # --- Add weekly view buttons ---
    first_day_of_month = datetime(year, month, 1).date()
    # Find the Monday of the first week
    start_of_first_week = first_day_of_month - timedelta(days=first_day_of_month.weekday())
    
    current_week_start = start_of_first_week
    while current_week_start.month <= month:
        week_end = current_week_start + timedelta(days=6)
        label = translator.gettext(lang, "schedule_view_week", start=current_week_start.strftime('%d.%m'), end=week_end.strftime('%d.%m'))
        callback_data = f"sch_week_:{entity_type}:{entity_id}:{current_week_start.strftime('%Y-%m-%d')}"
        builder.row(InlineKeyboardButton(text=label, callback_data=callback_data))
        current_week_start += timedelta(weeks=1)
        if current_week_start.year > year: break # Stop if we roll into the next year

    # Add a "Today" button to quickly jump back to the current month
    today_btn_text = translator.gettext(lang, "schedule_date_today")
    builder.row(InlineKeyboardButton(
        text=today_btn_text,
        callback_data=f"cal_nav:today:0:0:{entity_type}:{entity_id}" # Year/month are placeholders
    ))

    # Add a "Back to Search Results" button
    back_btn_text = translator.gettext(lang, "schedule_back_to_results")
    builder.row(InlineKeyboardButton(text=back_btn_text, callback_data="sch_back_to_results"))


    return builder.as_markup()

def get_modules_keyboard(available_modules: list[str], selected_modules: list[str], sub_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    # Сортируем модули, чтобы порядок кнопок не скакал
    for mod in sorted(available_modules):
        is_selected = mod in selected_modules
        # Если список selected_modules пустой, значит пользователь еще не выбирал -> выбираем ВСЕ по умолчанию?
        # Или наоборот: если он пуст, значит ничего не выбрано. 
        # В моей логике: если список пуст в БД, значит фильтр выключен (показываем всё). 
        # Но здесь для UI мы показываем галочки.
        
        icon = "✅" if is_selected else "❌"
        
        # Генерируем хэш для callback data (ограничение Telegram 64 байта)
        mod_hash = hashlib.md5(mod.encode()).hexdigest()[:8]
        
        builder.row(InlineKeyboardButton(
            text=f"{icon} {mod}", 
            callback_data=f"mod_toggle:{sub_id}:{mod_hash}"
        ))
        
    builder.row(InlineKeyboardButton(text="💾 Сохранить выбор", callback_data=f"mod_save:{sub_id}"))
    return builder.as_markup()

# Константы для фильтров
FILTER_TYPES_MAP = {
    'Lecture': 'Лекции',
    'Seminar': 'Семинары',
    'Exam': 'Экзамены/Зачеты'
}

def get_myschedule_calendar_keyboard(year: int, month: int, lang: str, busy_days: dict) -> InlineKeyboardMarkup:
    """
    busy_days: dict { day_int: 'marker_char' } 
    marker_char: '•' (обычно), '❗️' (экзамен)
    """
    builder = InlineKeyboardBuilder()
    
    # 1. Навигация
    month_names = translator.gettext(lang, "calendar_months").split(',')
    month_name = month_names[month - 1]
    
    builder.row(
        InlineKeyboardButton(text="⚙️ Фильтры", callback_data="mysch_filters:main"),
        InlineKeyboardButton(text=f"{month_name} {year}", callback_data="noop")
    )
    
    # Стрелки
    builder.row(
        InlineKeyboardButton(text="<<", callback_data=f"mysch_nav:prev:{year}:{month}"),
        InlineKeyboardButton(text="Сегодня", callback_data=f"mysch_nav:today:0:0"),
        InlineKeyboardButton(text=">>", callback_data=f"mysch_nav:next:{year}:{month}")
    )

    # Дни недели
    day_names = translator.gettext(lang, "calendar_days_short").split(',')
    builder.row(*[InlineKeyboardButton(text=day, callback_data="noop") for day in day_names])

    # Сетка
    month_calendar = calendar.monthcalendar(year, month)
    for week in month_calendar:
        row_buttons = []
        for day in week:
            if day == 0:
                row_buttons.append(InlineKeyboardButton(text=" ", callback_data="noop"))
            else:
                marker = busy_days.get(day, "")
                text = f"{day}{marker}"
                # callback: action : year : month : day
                row_buttons.append(InlineKeyboardButton(text=text, callback_data=f"mysch_day:{year}:{month}:{day}"))
        builder.row(*row_buttons)

    return builder.as_markup()

def get_myschedule_filters_keyboard(filter_config: dict, subscriptions: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    excluded_subs = filter_config.get('excluded_subs', [])
    excluded_types = filter_config.get('excluded_types', [])

    # 1. Фильтры по Типам
    builder.row(InlineKeyboardButton(text="--- Типы занятий ---", callback_data="noop"))
    for f_code, f_name in FILTER_TYPES_MAP.items():
        state = "❌" if f_code in excluded_types else "✅"
        builder.row(InlineKeyboardButton(
            text=f"{state} {f_name}", 
            callback_data=f"mysch_tog_type:{f_code}"
        ))

    # 2. Фильтры по Источникам
    if len(subscriptions) > 1: # Показываем, только если есть из чего выбирать
        builder.row(InlineKeyboardButton(text="--- Источники ---", callback_data="noop"))
        for sub in subscriptions:
            state = "❌" if sub['id'] in excluded_subs else "✅"
            # Обрезаем имя, если слишком длинное
            name = sub['entity_name'][:20] + "..." if len(sub['entity_name']) > 20 else sub['entity_name']
            builder.row(InlineKeyboardButton(
                text=f"{state} {name}", 
                callback_data=f"mysch_tog_sub:{sub['id']}"
            ))

    builder.row(InlineKeyboardButton(text="⬅️ Назад к календарю", callback_data="mysch_back_cal"))
    return builder.as_markup()
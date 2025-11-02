import logging
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from cachetools import LRUCache
import hashlib
import matplobblib
import os # Import os to access environment variables like ADMIN_USER_ID
from typing import List, Dict, Any
from . import database # Import database to check for user repos
from shared_lib.i18n import translator

logger = logging.getLogger(__name__)

# Define base commands that are always available
BASE_COMMANDS = ['/matp_all', '/matp_search', '/lec_search', '/lec_all', '/favorites', '/settings', '/help', '/latex', '/mermaid']
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
    except Exception as e:
        logger.error(f"Ошибка генерации данных для подмодуля {submodule_name}: {e}", exc_info=True)

logger.info("Завершение генерации данных для клавиатур тем и задач.")

def _get_user_commands(user_id: int) -> list[str]:
    """Helper to get commands for a user."""
    commands = list(BASE_COMMANDS)
    admin_id_str = os.getenv('ADMIN_USER_ID')
    if admin_id_str and user_id == int(admin_id_str):
        commands.extend(ADMIN_COMMANDS)
    return commands

# Function to get the main ReplyKeyboardMarkup (used for /start, after /code)
async def get_main_reply_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    current_commands = _get_user_commands(user_id)
    keyboard_buttons = [[KeyboardButton(text=cmd)] for cmd in current_commands]
    lang = await translator.get_user_language(user_id)
    return ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True,
        input_field_placeholder=translator.gettext(lang, 'main_menu_placeholder'),
        one_time_keyboard=True,
    )






# Function to get the help InlineKeyboardMarkup
async def get_help_inline_keyboard(user_id: int) -> InlineKeyboardMarkup:
    lang = await translator.get_user_language(user_id)

    inline_keyboard_rows = [
        [InlineKeyboardButton(text=translator.gettext(lang, "help_btn_matp_all"), callback_data="help_cmd_matp_all")],
        [InlineKeyboardButton(text=translator.gettext(lang, "help_btn_matp_search"), callback_data="help_cmd_matp_search")],
        [InlineKeyboardButton(text=translator.gettext(lang, "help_btn_lec_search"), callback_data="help_cmd_lec_search")],
        [InlineKeyboardButton(text=translator.gettext(lang, "help_btn_lec_all"), callback_data="help_cmd_lec_all")],
        [InlineKeyboardButton(text=translator.gettext(lang, "help_btn_favorites"), callback_data="help_cmd_favorites")],
        [InlineKeyboardButton(text=translator.gettext(lang, "help_btn_settings"), callback_data="help_cmd_settings")],
        [InlineKeyboardButton(text=translator.gettext(lang, "help_btn_latex"), callback_data="help_cmd_latex")],
        [InlineKeyboardButton(text=translator.gettext(lang, "help_btn_mermaid"), callback_data="help_cmd_mermaid")]
    ]
    admin_id = os.getenv('ADMIN_USER_ID')
    if admin_id and user_id == int(admin_id):
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

async def get_repo_management_keyboard(user_id: int, state: FSMContext | None = None) -> InlineKeyboardMarkup:
    """Creates an inline keyboard for managing user repositories."""
    lang = await translator.get_user_language(user_id)
    repos = await database.get_user_repos(user_id)
    builder = InlineKeyboardBuilder()
    current_state_str = await state.get_state() if state else None

    for repo_path in repos:
        repo_hash = hashlib.sha1(repo_path.encode()).hexdigest()[:16]
        code_path_cache[repo_hash] = repo_path
        builder.row(
            InlineKeyboardButton(text=f"Repo: {repo_path}", callback_data="noop"),
            InlineKeyboardButton(text="✏️", callback_data=f"repo_edit_hash:{repo_hash}"),
            InlineKeyboardButton(text=translator.gettext(lang, "favorites_remove_btn"), callback_data=f"repo_del_hash:{repo_hash}")
        )
    builder.row(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_add_repo"), callback_data="repo_add_new"))
    
    # Conditionally add the correct "back" button
    if current_state_str == "onboarding:step2":
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_back_to_tour"), callback_data="onboarding_next"))
    else:
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "back_to_settings"), callback_data="back_to_settings"))
    return builder.as_markup()



async def get_schedule_type_keyboard(lang: str) -> InlineKeyboardMarkup:
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
    return builder.as_markup()

def build_search_results_keyboard(results: List[Dict[str, Any]], search_type: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in results[:20]: # Limit to 20 results to avoid hitting Telegram limits
        builder.row(
            InlineKeyboardButton(
                text=item['label'], 
                callback_data=f"sch_result_:{item.get('type', search_type)}:{item['id']}"
            )
        )
    return builder.as_markup()
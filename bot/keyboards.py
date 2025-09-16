import logging
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from cachetools import LRUCache
import hashlib
import matplobblib
import os # Import os to access environment variables like ADMIN_USER_ID

logger = logging.getLogger(__name__)

# Define base commands that are always available
BASE_COMMANDS = ['/ask', '/search', '/search_md', '/abstracts', '/favorites', '/settings', '/settings_latex', '/help', '/execute', '/latex']
ADMIN_COMMANDS = ['/update']

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
def get_main_reply_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    current_commands = _get_user_commands(user_id)
    keyboard_buttons = [[KeyboardButton(text=cmd)] for cmd in current_commands]
    return ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True,
        input_field_placeholder='Что выберем, хозяин?',
        one_time_keyboard=True,
    )

# Function to get the submodules ReplyKeyboardMarkup
def get_submodules_reply_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    keyboard_buttons = [[KeyboardButton(text=i)] for i in matplobblib.submodules]
    keyboard_buttons.append([KeyboardButton(text="Отмена")])
    return ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True,
        input_field_placeholder='Выберите подмодуль или нажмите "Отмена"',
        one_time_keyboard=True,
    )

# Function to get the topics ReplyKeyboardMarkup for a specific submodule
def get_topics_reply_keyboard(user_id: int, submodule_name: str) -> ReplyKeyboardMarkup:
    topics = topics_data.get(submodule_name, {}).get('topics', [])
    keyboard_buttons = [[KeyboardButton(text=i)] for i in topics]
    keyboard_buttons.append([KeyboardButton(text="Отмена")])
    return ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True,
        input_field_placeholder='Выберите тему или нажмите "Отмена"',
        one_time_keyboard=True,
    )

# Function to get the codes ReplyKeyboardMarkup for a specific submodule and topic
def get_codes_reply_keyboard(user_id: int, submodule_name: str, topic_name: str) -> ReplyKeyboardMarkup:
    codes = topics_data.get(submodule_name, {}).get('codes', {}).get(topic_name, [])
    keyboard_buttons = [[KeyboardButton(text=i)] for i in codes]
    keyboard_buttons.append([KeyboardButton(text="Отмена")])
    return ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True,
        input_field_placeholder='Выберите задачу или нажмите "Отмена"',
        one_time_keyboard=True,
    )


# Function to get the help InlineKeyboardMarkup
def get_help_inline_keyboard(user_id: int) -> InlineKeyboardMarkup:
    inline_keyboard_rows = [
        [InlineKeyboardButton(text="❓ /ask - Начать поиск", callback_data="help_cmd_ask")],
        [InlineKeyboardButton(text="🔍 /search - Поиск по библиотеке", callback_data="help_cmd_search")],
        [InlineKeyboardButton(text="📚 /search_md - Поиск по конспектам", callback_data="help_cmd_search_md")],
        [InlineKeyboardButton(text="📂 /abstracts - Просмотр конспектов", callback_data="help_cmd_abstracts")],
        [InlineKeyboardButton(text="⭐ /favorites - Избранное", callback_data="help_cmd_favorites")],
        [InlineKeyboardButton(text="⚙️ /settings - Настройки", callback_data="help_cmd_settings")],
        [InlineKeyboardButton(text="📐 /settings_latex - Настройки LaTeX", callback_data="help_cmd_settings_latex")],
        [InlineKeyboardButton(text="▶️ /execute - Выполнить код", callback_data="help_cmd_execute")],
        [InlineKeyboardButton(text="🧮 /latex - Рендер LaTeX", callback_data="help_cmd_latex")]
    ]
    admin_id = os.getenv('ADMIN_USER_ID')
    if admin_id and user_id == int(admin_id):
        inline_keyboard_rows.append( [InlineKeyboardButton(text="🔄 /update - Обновить (admin)", callback_data="help_cmd_update")])
    
    inline_keyboard_rows.append([InlineKeyboardButton(text="ℹ️ /help - Эта справка", callback_data="help_cmd_help")])
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

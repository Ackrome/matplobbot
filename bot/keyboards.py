import logging
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from cachetools import LRUCache
import hashlib
import matplobblib
import os # Import os to access environment variables like ADMIN_USER_ID
from . import database # Import database to check for user repos

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






# Function to get the help InlineKeyboardMarkup
def get_help_inline_keyboard(user_id: int) -> InlineKeyboardMarkup:
    inline_keyboard_rows = [
        [InlineKeyboardButton(text="📂 /matp_all - Просмотр библиотеки", callback_data="help_cmd_matp_all")],
        [InlineKeyboardButton(text="🔍 /matp_search - Поиск по библиотеке", callback_data="help_cmd_matp_search")],
        [InlineKeyboardButton(text="📚 /lec_search - Поиск по конспектам", callback_data="help_cmd_lec_search")],
        [InlineKeyboardButton(text="📂 /lec_all - Просмотр конспектов", callback_data="help_cmd_lec_all")],
        [InlineKeyboardButton(text="⭐ /favorites - Избранное", callback_data="help_cmd_favorites")],
        [InlineKeyboardButton(text="⚙️ /settings - Настройки", callback_data="help_cmd_settings")],
        [InlineKeyboardButton(text="🧮 /latex - Рендер LaTeX", callback_data="help_cmd_latex")],
        [InlineKeyboardButton(text="🎨 /mermaid - Рендер Mermaid", callback_data="help_cmd_mermaid")]
    ]
    admin_id = os.getenv('ADMIN_USER_ID')
    if admin_id and user_id == int(admin_id):
        inline_keyboard_rows.append([InlineKeyboardButton(text="🔄 /update - Обновить (admin)", callback_data="help_cmd_update")])
        inline_keyboard_rows.append([InlineKeyboardButton(text="🗑️ /clear_cache - Очистить кэш (admin)", callback_data="help_cmd_clear_cache")])
    
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

async def get_repo_management_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Creates an inline keyboard for managing user repositories."""
    repos = await database.get_user_repos(user_id)
    builder = InlineKeyboardBuilder()

    for repo_path in repos:
        repo_hash = hashlib.sha1(repo_path.encode()).hexdigest()[:16]
        code_path_cache[repo_hash] = repo_path
        builder.row(
            InlineKeyboardButton(text=f"Repo: {repo_path}", callback_data="noop"),
            InlineKeyboardButton(text="✏️", callback_data=f"repo_edit_hash:{repo_hash}"),
            InlineKeyboardButton(text="❌", callback_data=f"repo_del_hash:{repo_hash}")
        )
    builder.row(InlineKeyboardButton(text="➕ Добавить новый репозиторий", callback_data="repo_add_new"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад в настройки", callback_data="back_to_settings"))
    return builder.as_markup()

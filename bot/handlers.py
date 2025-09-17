import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, FSInputFile, BufferedInputFile
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
import aiohttp
from telegraph import Telegraph
from telegraph.exceptions import TelegraphException

import asyncio
import sys
import matplotlib
matplotlib.use('Agg') # Use a non-interactive backend for server environments
import matplobblib
import os
import pkg_resources
import re
import hashlib
from cachetools import TTLCache
# from main import logging

from . import database
from . import keyboards as kb
from . import service

SEARCH_RESULTS_PER_PAGE = 10

async def update_library_async(library_name):
    try:
        process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "pip", "install", "--upgrade", library_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            print(f"Библиотека '{library_name}' успешно обновлена! {stdout.decode()}")
            return True, f"Библиотека '{library_name}' успешно обновлена! Текущая версия: {pkg_resources.get_distribution('matplobblib').version}"
        else:
            print(f"Ошибка при обновлении библиотеки '{library_name}': {stderr.decode()}")
            return False, f"Ошибка при обновлении библиотеки '{library_name}': {stderr.decode()}"
    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")
        return False, f"Произошла непредвиденная ошибка: {e}"


router = Router()

# Cache for search results to avoid long callback_data
# {user_id: {'query': str, 'results': list}}
user_search_results_cache = {}

@router.message(CommandStart())
async def comand_start(message: Message):
    await message.answer(
        f'Привет, {message.from_user.full_name}!',
        reply_markup=kb.get_main_reply_keyboard(message.from_user.id)
    )
    
@router.message(Command('help'))
async def comand_help(message: Message):
    await message.answer(
        'Это бот для поиска примеров кода по библиотеке matplobblib.\n\n'
        'Нажмите на кнопку, чтобы выполнить команду:',
        reply_markup=kb.get_help_inline_keyboard(message.from_user.id)
    )

@router.message(StateFilter('*'), Command("cancel"))
@router.message(StateFilter('*'), F.text.casefold() == "отмена")
async def cancel_handler(message: Message, state: FSMContext) -> None:
    """
    Позволяет пользователю отменить любое действие (выйти из любого состояния).
    """
    current_state = await state.get_state()
    if current_state is None:
        await message.answer(
            "Нет активной команды для отмены.",
            reply_markup=kb.get_main_reply_keyboard(message.from_user.id)
        )
        return

    logging.info(f"Cancelling state {current_state} for user {message.from_user.id}")
    await state.clear()
    # Убираем клавиатуру предыдущего шага и ставим основную
    await message.answer(
        "Действие отменено.",
        reply_markup=kb.get_main_reply_keyboard(message.from_user.id),
    )

##################################################################################################
# ASK
##################################################################################################
class Search(StatesGroup):
    query = State()

class MarkdownSearch(StatesGroup):
    query = State()

class LatexRender(StatesGroup):
    formula = State()

async def display_matp_all_navigation(message: Message, path: str = "", page: int = 0, is_edit: bool = False):
    """Helper to display navigation for /matp_all command."""
    path_parts = path.split('.') if path else []
    level = len(path_parts)
    
    builder = InlineKeyboardBuilder()
    header_text = ""

    # Level 0: Submodules
    if level == 0:
        header_text = "Выберите подмодуль"
        items = sorted(matplobblib.submodules)
        # No pagination for submodules, assuming list is short
        for item in items:
            path_hash = hashlib.sha1(item.encode()).hexdigest()[:16]
            kb.code_path_cache[path_hash] = item
            builder.row(InlineKeyboardButton(text=f"📁 {item}", callback_data=f"matp_all_nav_hash:{path_hash}:0"))
    
    # Level 1: Topics
    elif level == 1:
        submodule = path_parts[0]
        header_text = f"Подмодуль `{submodule}`. Выберите тему"
        all_topics = sorted(kb.topics_data.get(submodule, {}).get('topics', []))
        
        start = page * SEARCH_RESULTS_PER_PAGE
        end = start + SEARCH_RESULTS_PER_PAGE
        page_items = all_topics[start:end]

        for item in page_items:
            full_path = f"{submodule}.{item}"
            path_hash = hashlib.sha1(full_path.encode()).hexdigest()[:16]
            kb.code_path_cache[path_hash] = full_path
            builder.row(InlineKeyboardButton(text=f"📚 {item}", callback_data=f"matp_all_nav_hash:{path_hash}:0"))
        
        # Back button
        builder.row(InlineKeyboardButton(text="⬅️ .. (Назад к подмодулям)", callback_data="matp_all_nav_hash:root:0"))
        
        total_pages = (len(all_topics) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE
        if total_pages > 1:
            pagination_buttons = []
            path_hash = hashlib.sha1(path.encode()).hexdigest()[:16]
            kb.code_path_cache[path_hash] = path
            if page > 0:
                pagination_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"matp_all_nav_hash:{path_hash}:{page - 1}"))
            pagination_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
            if end < len(all_topics):
                pagination_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"matp_all_nav_hash:{path_hash}:{page + 1}"))
            builder.row(*pagination_buttons)

    # Level 2: Codes
    elif level == 2:
        submodule, topic = path_parts
        header_text = f"Тема `{topic}`. Выберите задачу"
        all_codes = sorted(kb.topics_data.get(submodule, {}).get('codes', {}).get(topic, []))

        start = page * SEARCH_RESULTS_PER_PAGE
        end = start + SEARCH_RESULTS_PER_PAGE
        page_items = all_codes[start:end]

        for item in page_items:
            full_code_path = f"{path}.{item}"
            path_hash = hashlib.sha1(full_code_path.encode()).hexdigest()[:16]
            kb.code_path_cache[path_hash] = full_code_path
            builder.row(InlineKeyboardButton(text=f"📄 {item}", callback_data=f"matp_all_show:{path_hash}"))

        # Back button
        back_path = submodule
        path_hash = hashlib.sha1(back_path.encode()).hexdigest()[:16]
        kb.code_path_cache[path_hash] = back_path
        builder.row(InlineKeyboardButton(text=f"⬅️ .. (Назад к темам)", callback_data=f"matp_all_nav_hash:{path_hash}:0"))

        total_pages = (len(all_codes) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE
        if total_pages > 1:
            pagination_buttons = []
            path_hash = hashlib.sha1(path.encode()).hexdigest()[:16]
            kb.code_path_cache[path_hash] = path
            if page > 0:
                pagination_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"matp_all_nav_hash:{path_hash}:{page - 1}"))
            pagination_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
            if end < len(all_codes):
                pagination_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"matp_all_nav_hash:{path_hash}:{page + 1}"))
            builder.row(*pagination_buttons)

    else:
        header_text = "Ошибка навигации."

    reply_markup = builder.as_markup()
    
    if is_edit:
        try:
            await message.edit_text(header_text, reply_markup=reply_markup, parse_mode='markdown')
        except TelegramBadRequest as e:
            if "message is not modified" not in e.message:
                raise
    else:
        await message.answer(header_text, reply_markup=reply_markup, parse_mode='markdown')

@router.message(Command('matp_all'))
async def matp_all_command_inline(message: Message):
    """Handles the /matp_all command with inline navigation."""
    await display_matp_all_navigation(message, path="", page=0, is_edit=False)

@router.callback_query(F.data.startswith("matp_all_nav_hash:"))
async def cq_matp_all_navigate(callback: CallbackQuery):
    """Handles navigation for the /matp_all command."""
    parts = callback.data.split(":")
    path_hash = parts[1]
    page = int(parts[2])
    
    if path_hash == 'root':
        path = ""
    else:
        path = kb.code_path_cache.get(path_hash)

    if path is None:
        await callback.answer("Ошибка: информация о навигации устарела. Пожалуйста, начните с /matp_all.", show_alert=True)
        return

    await callback.answer()
    await display_matp_all_navigation(callback.message, path=path, page=page, is_edit=True)

@router.callback_query(F.data.startswith("matp_all_show:"))
async def cq_matp_all_show_code(callback: CallbackQuery):
    """Shows the selected code from the /matp_all navigation."""
    path_hash = callback.data.split(":", 1)[1]
    code_path = kb.code_path_cache.get(path_hash)
    if not code_path:
        await callback.answer("Ошибка: информация о коде устарела. Пожалуйста, начните с /matp_all.", show_alert=True)
        return
    
    await callback.answer()
    await service.show_code_by_path(callback.message, callback.from_user.id, code_path, "Выбранный пример")

##################################################################################################
# UPDATE
##################################################################################################
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID'))

@router.message(Command('update'))
async def update(message: Message):
    if message.from_user.id != ADMIN_USER_ID:
        await message.reply("У вас нет прав на использование этой команды.", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))
        return

    status_msg = await message.answer("Начинаю обновление библиотеки `matplobblib`...")
    # Можно добавить 
    # await message.answer_chat_action("typing")
    success, status_message_text = await update_library_async('matplobblib')
    if success:
        # Перезагрузка модуля matplobblib, если это необходимо для немедленного применения изменений
        import importlib
        importlib.reload(matplobblib) # Может быть сложным и иметь побочные эффекты
        await status_msg.edit_text(status_message_text) # Убран reply_markup
    else:
        await status_msg.edit_text(status_message_text) # Убран reply_markup
    
    await message.answer("Обновление завершено. Выберите следующую команду:", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))
##################################################################################################
# CLEAR CACHE
##################################################################################################
@router.message(Command('clear_cache'))
async def clear_cache_command(message: Message):
    """Handles the /clear_cache command, admin-only. Clears all application caches."""
    if message.from_user.id != ADMIN_USER_ID:
        await message.reply("У вас нет прав на использование этой команды.", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))
        return

    status_msg = await message.answer("Начинаю очистку кэша...")

    # 1. Clear in-memory caches in handlers.py
    user_search_results_cache.clear()
    md_search_results_cache.clear()
    github_search_cache.clear()
    
    # 2. Clear in-memory caches from other modules
    kb.code_path_cache.clear()
    service.github_content_cache.clear()
    service.github_dir_cache.clear()

    # 3. Clear persistent cache in database
    await database.clear_latex_cache()

    await status_msg.edit_text("✅ Весь кэш приложения был успешно очищен.")
    await message.answer("Выберите следующую команду:", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))
##################################################################################################
# EXECUTE
##################################################################################################
class Execution(StatesGroup):
    code = State()
EXECUTE_HELP_TEXT = (
    "Пожалуйста, отправьте код Python для выполнения. Если ваш код генерирует изображения (например, с помощью `matplotlib.pyplot.savefig`), они будут отправлены вам.\n\n"
    "**Поддерживаемый вывод:**\n"
    "1.  **Текстовый вывод** (stdout/stderr).\n"
    "2.  **Изображения**, сохраненные в файл (png, jpg, jpeg, gif).\n"
    "3.  **Форматированный текст** (Markdown/HTML).\n\n"
    "**Пример с Matplotlib:**\n"
    "```python\n"
    "import matplotlib.pyplot as plt\n"
    "plt.plot([1, 2, 3], [1, 4, 9])\n"
    "plt.savefig('my_plot.png')\n"
    "plt.close()\n"
    "```\n\n"
    "**Пример с форматированным текстом:**\n"
    "Функции `display`, `Markdown`, `HTML` доступны без импорта.\n"
    "```python\n"
    "display(Markdown('# Заголовок 1\\n## Заголовок 2\\n*Курсив*'))\n"
    "```"
)

@router.message(Command('execute'))
async def execute_command(message: Message, state: FSMContext):
    # """Handles the /execute command, admin-only."""
    # if message.from_user.id != ADMIN_USER_ID:
    #     await message.reply("У вас нет прав на использование этой команды.", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))
    #     return

    await state.set_state(Execution.code)
    await message.answer(
        EXECUTE_HELP_TEXT,
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='markdown'
    )

@router.message(Execution.code)
async def process_execution_from_user(message: Message, state: FSMContext):
    """Executes the received Python code and sends back the output, including images and rich display objects."""
    await state.clear()
    await service.execute_code_and_send_results(message, message.text)

##################################################################################################
# LATEX
##################################################################################################

@router.message(Command('latex'))
async def latex_command(message: Message, state: FSMContext):
    await state.set_state(LatexRender.formula)
    await message.answer(
        "Пожалуйста, отправьте вашу формулу в синтаксисе LaTeX (можно без внешних `$...`):",
        reply_markup=ReplyKeyboardRemove()
    )

@router.message(LatexRender.formula)
async def process_latex_formula(message: Message, state: FSMContext):
    await state.clear()
    formula = message.text
    
    status_msg = await message.answer("🖼️ Рендеринг формулы...")

    try:
        settings = await database.get_user_settings(message.from_user.id)
        padding = settings['latex_padding']
        image_buffer = await service.render_latex_to_image(formula, padding)
        
        await status_msg.delete()
        await message.answer_photo(
            photo=BufferedInputFile(image_buffer.read(), filename="formula.png"),
            caption=f"Ваша формула:\n`{formula}`",
            parse_mode='markdown'
        )
        await message.answer("Готово! Выберите следующую команду:", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))

    except (ValueError, RuntimeError, FileNotFoundError) as e:
        logging.error(f"Ошибка при рендеринге LaTeX для '{formula}': {e}", exc_info=True)
        # Используем Markdown для форматирования ошибки
        error_text = f"Не удалось отрендерить формулу.\n\n**Ошибка:**\n```\n{e}\n```\n\nУбедитесь, что синтаксис корректен."
        await status_msg.edit_text(error_text, parse_mode='markdown')
    except Exception as e:
        logging.error(f"Непредвиденная ошибка при рендеринге LaTeX для '{formula}': {e}", exc_info=True)
        await status_msg.edit_text(
            f"Произошла непредвиденная ошибка: {e}"
        )

##################################################################################################
# MARKDOWN SEARCH & ABSTRACTS
##################################################################################################

# Cache for markdown search results
# {user_id: {'query': str, 'results': list[dict]}}
md_search_results_cache = {}
# Cache for GitHub markdown search results to reduce API calls
github_search_cache = TTLCache(maxsize=100, ttl=600) # Cache search results for 10 minutes



@router.message(Command('lec_all'))
async def lec_all_command(message: Message):
    """Handles the /lec_all command, showing root of the repo."""
    await service.display_lec_all_path(message, path="")

@router.callback_query(F.data.startswith("abs_nav_hash:"))
async def cq_lec_all_navigate(callback: CallbackQuery):
    """Handles navigation through lec_all repo directories."""
    path_hash = callback.data.split(":", 1)[1]
    path = kb.code_path_cache.get(path_hash)

    if path is None: # Important to check for None, as "" is a valid path (root)
        await callback.answer("Информация о навигации устарела. Пожалуйста, начните с /lec_all.", show_alert=True)
        return

    await callback.answer()
    await service.display_lec_all_path(callback.message, path, is_edit=True)

@router.callback_query(F.data.startswith("abs_show_hash:"))
async def cq_lec_all_show_file(callback: CallbackQuery):
    """Calls the helper to display a file from the lec_all repo."""
    path_hash = callback.data.split(":", 1)[1]
    file_path = kb.code_path_cache.get(path_hash)

    if not file_path:
        await callback.answer("Информация о файле устарела. Пожалуйста, обновите навигацию.", show_alert=True)
        return

    await service.display_github_file(callback, file_path)

async def get_md_search_results_keyboard(user_id: int, page: int = 0) -> InlineKeyboardMarkup | None:
    """Создает инлайн-клавиатуру для страницы результатов поиска по конспектам с пагинацией."""
    search_data = md_search_results_cache.get(user_id)
    if not search_data or not search_data.get('results'):
        return None

    results = search_data['results']
    builder = InlineKeyboardBuilder()
    
    start = page * SEARCH_RESULTS_PER_PAGE
    end = start + SEARCH_RESULTS_PER_PAGE
    page_items = results[start:end]

    for i, item in enumerate(page_items):
        # Используем хэш для callback_data, чтобы избежать превышения лимита длины
        path_hash = hashlib.sha1(item['path'].encode()).hexdigest()[:16]
        kb.code_path_cache[path_hash] = item['path']
        builder.row(InlineKeyboardButton(
            text=f"📄 {item['path']}",
            callback_data=f"show_md_hash:{path_hash}"
        ))

    # Элементы управления пагинацией
    total_pages = (len(results) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE
    if total_pages > 1:
        pagination_buttons = []
        if page > 0:
            pagination_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"md_search_page:{page - 1}"))
        
        pagination_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))

        if end < len(results):
            pagination_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"md_search_page:{page + 1}"))
        
        builder.row(*pagination_buttons)

    return builder.as_markup()


async def search_github_md(query: str) -> list[dict] | None:
    """Searches for markdown files in a specific GitHub repository."""
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        logging.error("GITHUB_TOKEN environment variable not set. Markdown search is disabled.")
        return None
    MD_SEARCH_REPO = "kvdep/Abstracts"
    search_query = f"{query} repo:{MD_SEARCH_REPO} extension:md"
    url = "https://api.github.com/search/code"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {github_token}"
    }
    params = {"q": search_query, "per_page": 100} # Get up to 100 results

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("items", [])
                    # Store in cache on success
                    github_search_cache[query] = results
                    return results
                else:
                    error_text = await response.text()
                    logging.error(f"GitHub API search failed with status {response.status}: {error_text}")
                    return None
    except Exception as e:
        logging.error(f"Error during GitHub API request: {e}", exc_info=True)
        return None

@router.message(Command('lec_search'))
async def lec_search_command(message: Message, state: FSMContext):
    """Handles the /lec_search command."""
    await state.set_state(MarkdownSearch.query)
    await message.answer("Введите ключевые слова для поиска по конспектам:", reply_markup=ReplyKeyboardRemove())

@router.message(MarkdownSearch.query)
async def process_md_search_query(message: Message, state: FSMContext):
    """Processes the user's query for markdown files."""
    await state.clear()
    query = message.text
    status_msg = await message.answer(f"Идет поиск конспектов по запросу '{query}'...")

    results = await search_github_md(query)

    if results is None:
        await status_msg.edit_text("Произошла ошибка при поиске. Попробуйте позже.")
        await message.answer("Выберите следующую команду:", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))
        return

    if not results:
        await status_msg.edit_text(f"По вашему запросу '{query}' ничего не найдено.")
        await message.answer("Выберите следующую команду:", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))
        return

    user_id = message.from_user.id
    md_search_results_cache[user_id] = {'query': query, 'results': results}

    keyboard = await get_md_search_results_keyboard(user_id, page=0)
    total_pages = (len(results) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE

    await status_msg.edit_text(
        f"Найдено {len(results)} конспектов по запросу '{query}'. Страница 1/{total_pages}:",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("md_search_page:"))
async def cq_md_search_pagination(callback: CallbackQuery):
    """Обрабатывает нажатия на кнопки пагинации в результатах поиска по конспектам."""
    user_id = callback.from_user.id
    search_data = md_search_results_cache.get(user_id)
    if not search_data:
        await callback.answer("Результаты поиска устарели. Пожалуйста, выполните поиск заново.", show_alert=True)
        await callback.message.delete()
        return

    page = int(callback.data.split(":", 1)[1])
    keyboard = await get_md_search_results_keyboard(user_id, page=page)
    
    results = search_data['results']
    query = search_data['query']
    total_pages = (len(results) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE

    try:
        await callback.message.edit_text(
            f"Найдено {len(results)} конспектов по запросу '{query}'. Страница {page + 1}/{total_pages}:",
            reply_markup=keyboard
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in e.message:
            raise
    finally:
        await callback.answer()

@router.callback_query(F.data.startswith("show_md_hash:"))
async def cq_show_md_result(callback: CallbackQuery):
    """Fetches and displays the content of a markdown file from GitHub search results."""
    path_hash = callback.data.split(":", 1)[1]
    file_path = kb.code_path_cache.get(path_hash)

    if not file_path:
        await callback.answer("Информация о файле устарела. Пожалуйста, выполните поиск заново.", show_alert=True)
        return

    await service.display_github_file(callback, file_path)

##################################################################################################
# SEARCH & FAVORITES
##################################################################################################

async def get_search_results_keyboard(user_id: int, page: int = 0) -> InlineKeyboardMarkup | None:
    """Создает инлайн-клавиатуру для страницы результатов поиска с пагинацией."""
    search_data = user_search_results_cache.get(user_id)
    if not search_data or not search_data.get('results'):
        return None

    results = search_data['results']
    builder = InlineKeyboardBuilder()
    
    start = page * SEARCH_RESULTS_PER_PAGE
    end = start + SEARCH_RESULTS_PER_PAGE
    page_items = results[start:end]

    for i, result in enumerate(page_items):
        global_index = start + i
        builder.row(InlineKeyboardButton(
            text=f"▶️ {result['path']}", 
            callback_data=f"show_search_idx:{global_index}"
        ))

    # Pagination controls
    total_pages = (len(results) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE
    if total_pages > 1:
        pagination_buttons = []
        if page > 0:
            pagination_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"search_page:{page - 1}"))
        
        pagination_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))

        if end < len(results):
            pagination_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"search_page:{page + 1}"))
        
        builder.row(*pagination_buttons)

    return builder.as_markup()

async def perform_full_text_search(query: str) -> list[dict]:
    """
    Выполняет полнотекстовый поиск по всем примерам кода в matplobblib.
    Ищет в названиях подмодулей, тем, кода и в содержимом кода.
    Поддерживает поиск по нескольким ключевым словам (все должны присутствовать).
    """
    keywords = query.lower().split()
    if not keywords:
        return []

    found_items = []
    found_paths = set() # Для избежания дубликатов

    for submodule_name in matplobblib.submodules:
        try:
            module = matplobblib._importlib.import_module(f'matplobblib.{submodule_name}')
            # Ищем в полном словаре (с docstrings) для получения большего контекста
            code_dictionary = module.themes_list_dicts_full

            for topic_name, codes in code_dictionary.items():
                for code_name, code_content in codes.items():
                    code_path = f"{submodule_name}.{topic_name}.{code_name}"

                    if code_path in found_paths:
                        continue

                    # Создаем текстовый корпус для поиска
                    search_corpus = f"{submodule_name} {topic_name} {code_name} {code_content}".lower()

                    # Проверяем, что ВСЕ ключевые слова есть в корпусе
                    if all(keyword in search_corpus for keyword in keywords):
                        found_items.append({
                            'path': code_path,
                            'name': code_name
                        })
                        found_paths.add(code_path)

        except Exception as e:
            logging.error(f"Ошибка при поиске в подмодуле {submodule_name}: {e}")

    return found_items

@router.message(Command('matp_search'))
async def search_command(message: Message, state: FSMContext):
    await state.set_state(Search.query)
    await message.answer("Введите ключевые слова для поиска по примерам кода:", reply_markup=ReplyKeyboardRemove())

@router.message(Search.query)
async def process_search_query(message: Message, state: FSMContext):
    await state.clear()
    query = message.text
    status_msg = await message.answer(f"Идет поиск по запросу '{query}'...")
    results = await perform_full_text_search(query)

    if not results:
        await status_msg.edit_text(
            f"По вашему запросу '{query}' ничего не найдено.\n"
            "Попробуйте другие ключевые слова или воспользуйтесь командой /ask для пошагового выбора."
        )
        # Отправляем основную клавиатуру отдельным сообщением, так как edit_text не может ее использовать
        await message.answer("Выберите следующую команду:", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))
        return

    # Store query and results in cache for this user
    user_id = message.from_user.id
    user_search_results_cache[user_id] = {'query': query, 'results': results}

    keyboard = await get_search_results_keyboard(user_id, page=0)
    total_pages = (len(results) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE

    await status_msg.edit_text(
        f"Найдено {len(results)} примеров по запросу '{query}'. Страница 1/{total_pages}:",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("search_page:"))
async def cq_search_pagination(callback: CallbackQuery):
    """Обрабатывает нажатия на кнопки пагинации в результатах поиска."""
    user_id = callback.from_user.id
    search_data = user_search_results_cache.get(user_id)
    if not search_data:
        await callback.answer("Результаты поиска устарели. Пожалуйста, выполните поиск заново.", show_alert=True)
        await callback.message.delete()
        return

    page = int(callback.data.split(":", 1)[1])
    keyboard = await get_search_results_keyboard(user_id, page=page)
    
    results = search_data['results']
    query = search_data['query']
    total_pages = (len(results) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE

    await callback.message.edit_text(
        f"Найдено {len(results)} примеров по запросу '{query}'. Страница {page + 1}/{total_pages}:",
        reply_markup=keyboard
    )
    await callback.answer()

@router.message(Command('favorites'))
async def favorites_command(message: Message):
    user_id = message.from_user.id
    favs = await database.get_favorites(user_id)
    if not favs:
        await message.answer("У вас пока нет избранных примеров. Вы можете добавить их, нажав на кнопку '⭐ В избранное' под примером кода.", reply_markup=kb.get_main_reply_keyboard(user_id))
        return

    builder = InlineKeyboardBuilder()
    for code_path in favs:
        path_hash = hashlib.sha1(code_path.encode()).hexdigest()[:16]
        kb.code_path_cache[path_hash] = code_path
        builder.row(
            InlineKeyboardButton(text=f"📄 {code_path}", callback_data=f"show_fav_hash:{path_hash}"),
            InlineKeyboardButton(text="❌ Удалить", callback_data=f"fav_del_hash:{path_hash}")
        )
    
    await message.answer("Ваши избранные примеры:", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("fav_hash:"))
async def cq_add_favorite(callback: CallbackQuery):
    path_hash = callback.data.split(":", 1)[1]
    code_path = kb.code_path_cache.get(path_hash)
    if not code_path:
        await callback.answer("Ошибка: информация о коде устарела. Пожалуйста, запросите код заново.", show_alert=True)
        return

    success = await database.add_favorite(callback.from_user.id, code_path)
    if success:
        await callback.answer("✅ Добавлено в избранное!", show_alert=False)
    else:
        await callback.answer("Уже в избранном.", show_alert=False)

@router.callback_query(F.data.startswith("fav_del_hash:"))
async def cq_delete_favorite(callback: CallbackQuery):
    """Обрабатывает удаление примера из избранного."""
    user_id = callback.from_user.id
    path_hash = callback.data.split(":", 1)[1]
    code_path = kb.code_path_cache.get(path_hash)

    if not code_path:
        await callback.answer("Ошибка: информация об избранном устарела. Пожалуйста, вызовите /favorites снова.", show_alert=True)
        return

    # Удаляем из БД
    await database.remove_favorite(user_id, code_path)
    await callback.answer("Пример удален из избранного.", show_alert=False)

    # Обновляем сообщение со списком избранного
    favs = await database.get_favorites(user_id)
    if not favs:
        await callback.message.edit_text("Ваш список избранного пуст.")
        return

    # Пересобираем клавиатуру
    builder = InlineKeyboardBuilder()
    for new_code_path in favs:
        new_path_hash = hashlib.sha1(new_code_path.encode()).hexdigest()[:16]
        kb.code_path_cache[new_path_hash] = new_code_path
        builder.row(
            InlineKeyboardButton(text=f"📄 {new_code_path}", callback_data=f"show_fav_hash:{new_path_hash}"),
            InlineKeyboardButton(text="❌ Удалить", callback_data=f"fav_del_hash:{new_path_hash}")
        )
    
    try:
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    except TelegramBadRequest as e:
        if "message is not modified" not in e.message:
            logging.error(f"Ошибка при обновлении клавиатуры избранного: {e}")
            raise

@router.callback_query(F.data == "noop")
async def cq_noop(callback: CallbackQuery):
    """Пустой обработчик для кнопок, которые не должны ничего делать (например, счетчик страниц)."""
    await callback.answer()

@router.callback_query(F.data.startswith("show_search_idx:"))
async def cq_show_search_result_by_index(callback: CallbackQuery):
    """Handles clicks on search result buttons."""
    user_id = callback.from_user.id
    search_data = user_search_results_cache.get(user_id)
    if not search_data:
        await callback.answer("Результаты поиска устарели. Пожалуйста, выполните поиск заново.", show_alert=True)
        return

    try:
        index = int(callback.data.split(":", 1)[1])
        results = search_data['results']
        
        if not (0 <= index < len(results)):
            raise IndexError("Search result index out of bounds.")

        code_path = results[index]['path']
        
        await callback.answer() # Acknowledge the callback
        await service.show_code_by_path(callback.message, callback.from_user.id, code_path, "Результат поиска")

    except (ValueError, IndexError) as e:
        logging.warning(f"Invalid search index from user {user_id}. Data: {callback.data}. Error: {e}")
        await callback.answer("Неверный результат поиска. Возможно, он устарел.", show_alert=True)
    except Exception as e:
        logging.error(f"Error showing search result by index for user {user_id}: {e}", exc_info=True)
        await callback.answer("Произошла ошибка при отображении результата.", show_alert=True)

@router.callback_query(F.data.startswith("show_fav_hash:"))
async def cq_show_favorite(callback: CallbackQuery):
    """Handles clicks on favorite item buttons."""
    path_hash = callback.data.split(":", 1)[1]
    code_path = kb.code_path_cache.get(path_hash)
    if not code_path:
        await callback.answer("Ошибка: информация об избранном устарела. Пожалуйста, вызовите /favorites снова.", show_alert=True)
        return

    await callback.answer()
    await service.show_code_by_path(callback.message, callback.from_user.id, code_path, "Избранное")

@router.callback_query(F.data.startswith("run_hash:"))
async def cq_run_code_from_lib(callback: CallbackQuery):
    path_hash = callback.data.split(":", 1)[1]
    code_path = kb.code_path_cache.get(path_hash)
    if not code_path:
        await callback.answer("Ошибка: информация о коде устарела. Пожалуйста, запросите код заново.", show_alert=True)
        return

    submodule, topic, code_name = code_path.split('.')
    
    module = matplobblib._importlib.import_module(f'matplobblib.{submodule}')
    code_to_run = module.themes_list_dicts_full_nd[topic][code_name] # Берем код без docstring для корректного выполнения

    await callback.answer("▶️ Запускаю пример...")
    await service.execute_code_and_send_results(callback.message, code_to_run)
##################################################################################################
# SETTINGS
##################################################################################################

# Теперь эта функция асинхронная, так как обращается к БД
async def get_settings_keyboard(user_id: int) -> InlineKeyboardBuilder:
    """Создает инлайн-клавиатуру для настроек пользователя."""
    settings = await database.get_user_settings(user_id) # Теперь асинхронный вызов
    builder = InlineKeyboardBuilder()

    show_docstring_status = "✅ Вкл" if settings['show_docstring'] else "❌ Выкл"

    builder.row(
        InlineKeyboardButton(
            text=f"Показывать описание: {show_docstring_status}",
            callback_data="settings_toggle_docstring"
        )
    )

    # Настройка отображения Markdown
    md_mode = settings.get('md_display_mode', 'md_file')
    md_mode_map = {
        'telegraph': '🌐 Telegra.ph',
        'text': '📄 Простой текст',
        'md_file': '📁 .md файл',
        'html_file': '📁 .html файл'
    }
    md_mode_text = md_mode_map.get(md_mode, '❓ Неизвестно')

    builder.row(InlineKeyboardButton(
        text=f"Показ .md: {md_mode_text}",
        callback_data="settings_cycle_md_mode"
    ))

    # Настройка отступов LaTeX
    padding = settings['latex_padding']
    builder.row(
        InlineKeyboardButton(text="➖", callback_data="latex_padding_decr"),
        InlineKeyboardButton(text=f"Отступ LaTeX: {padding}px", callback_data="noop"),
        InlineKeyboardButton(text="➕", callback_data="latex_padding_incr")
    )
    return builder

@router.message(Command('settings'))
async def command_settings(message: Message):
    """Обработчик команды /settings."""
    keyboard = await get_settings_keyboard(message.from_user.id) # Теперь асинхронный вызов
    await message.answer(
        "⚙️ Настройки:",
        reply_markup=keyboard.as_markup()
    )

@router.callback_query(F.data == "settings_toggle_docstring")
async def cq_toggle_docstring(callback: CallbackQuery):
    """Обработчик для переключения настройки 'show_docstring'."""
    user_id = callback.from_user.id
    settings = await database.get_user_settings(user_id) # Теперь асинхронный вызов
    settings['show_docstring'] = not settings['show_docstring']
    await database.update_user_settings_db(user_id, settings) # Сохраняем обновленные настройки в БД
    keyboard = await get_settings_keyboard(user_id)
    await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
    await callback.answer("Настройка 'Показывать описание' обновлена.")

MD_DISPLAY_MODES = ['telegraph', 'text', 'md_file', 'html_file']

@router.callback_query(F.data == "settings_cycle_md_mode")
async def cq_cycle_md_mode(callback: CallbackQuery):
    """Обработчик для переключения режима отображения Markdown."""
    user_id = callback.from_user.id
    settings = await database.get_user_settings(user_id)

    current_mode = settings.get('md_display_mode', 'md_file')
    try:
        current_index = MD_DISPLAY_MODES.index(current_mode)
        next_index = (current_index + 1) % len(MD_DISPLAY_MODES)
        new_mode = MD_DISPLAY_MODES[next_index]
    except ValueError:
        # Если текущий режим некорректен, сбрасываем на дефолтный
        new_mode = MD_DISPLAY_MODES[0]

    settings['md_display_mode'] = new_mode
    await database.update_user_settings_db(user_id, settings)

    keyboard = await get_settings_keyboard(user_id)
    await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())

    md_mode_map = {
        'telegraph': '🌐 Telegra.ph',
        'text': '📄 Простой текст',
        'md_file': '📁 .md файл',
        'html_file': '📁 .html файл'
    }
    await callback.answer(f"Режим показа .md изменен на: {md_mode_map[new_mode]}")

##################################################################################################
# LATEX SETTINGS
##################################################################################################

@router.callback_query(F.data.startswith("latex_padding_"))
async def cq_change_latex_padding(callback: CallbackQuery):
    """Обработчик для изменения отступа LaTeX."""
    user_id = callback.from_user.id
    settings = await database.get_user_settings(user_id)
    current_padding = settings['latex_padding']

    action = callback.data.split('_')[-1]  # 'incr' or 'decr'
    new_padding = current_padding

    if action == "incr":
        new_padding += 5
    elif action == "decr":
        new_padding = max(0, current_padding - 5)

    if new_padding == current_padding:
        await callback.answer("Значение отступа не изменилось.")
        return

    settings['latex_padding'] = new_padding
    await database.update_user_settings_db(user_id, settings)

    keyboard = await get_settings_keyboard(user_id)
    await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
    await callback.answer(f"Отступ изменен на {new_padding}px")

##################################################################################################
# HELP COMMAND CALLBACKS
##################################################################################################

@router.callback_query(F.data == "help_cmd_matp_all")
async def cq_help_cmd_matp_all(callback: CallbackQuery):
    """Handler for '/matp_all' button from help menu."""
    await callback.answer()
    # Повторяем логику команды /matp_all
    await matp_all_command_inline(callback.message)

@router.callback_query(F.data == "help_cmd_matp_search")
async def cq_help_cmd_matp_search(callback: CallbackQuery, state: FSMContext):
    """Handler for '/matp_search' button from help menu."""
    await callback.answer()
    # Повторяем логику команды /matp_search
    await state.set_state(Search.query)
    await callback.message.answer("Введите ключевые слова для поиска по примерам кода:", reply_markup=ReplyKeyboardRemove())

@router.callback_query(F.data == "help_cmd_lec_search")
async def cq_help_cmd_lec_search(callback: CallbackQuery, state: FSMContext):
    """Handler for '/lec_search' button from help menu."""
    await callback.answer()
    # Повторяем логику команды /lec_search
    await state.set_state(MarkdownSearch.query)
    await callback.message.answer("Введите ключевые слова для поиска по конспектам:", reply_markup=ReplyKeyboardRemove())

@router.callback_query(F.data == "help_cmd_lec_all")
async def cq_help_cmd_lec_all(callback: CallbackQuery):
    """Handler for '/lec_all' button from help menu."""
    await callback.answer()
    await lec_all_command(callback.message)

@router.callback_query(F.data == "help_cmd_favorites")
async def cq_help_cmd_favorites(callback: CallbackQuery):
    """Handler for '/favorites' button from help menu."""
    await callback.answer()
    # Повторяем логику команды /favorites
    # favorites_command ожидает объект Message, callback.message подходит
    await favorites_command(callback.message)

@router.callback_query(F.data == "help_cmd_latex")
async def cq_help_cmd_latex(callback: CallbackQuery, state: FSMContext):
    """Handler for '/latex' button from help menu."""
    await callback.answer()
    # Повторяем логику команды /latex
    await latex_command(callback.message, state)

@router.callback_query(F.data == "help_cmd_settings")
async def cq_help_cmd_settings(callback: CallbackQuery):
    """Handler for '/settings' button from help menu."""
    await callback.answer()
    # Повторяем логику команды /settings
    keyboard = await get_settings_keyboard(callback.from_user.id)
    await callback.message.answer(
        "⚙️ Настройки:",
        reply_markup=keyboard.as_markup()
    )

@router.callback_query(F.data == "help_cmd_update")
async def cq_help_cmd_update(callback: CallbackQuery):
    """Handler for '/update' button from help menu."""
    if callback.from_user.id != ADMIN_USER_ID:
        await callback.answer("У вас нет прав на использование этой команды.", show_alert=True)
        return

    await callback.answer("Начинаю обновление...")
    
    # Повторяем логику команды /update
    status_msg = await callback.message.answer("Начинаю обновление библиотеки `matplobblib`...")
    success, status_message_text = await update_library_async('matplobblib')
    if success:
        import importlib
        importlib.reload(matplobblib)
        await status_msg.edit_text(status_message_text)
    else:
        await status_msg.edit_text(status_message_text)
    await callback.message.answer("Обновление завершено. Выберите следующую команду:", reply_markup=kb.get_main_reply_keyboard(callback.from_user.id))

@router.callback_query(F.data == "help_cmd_clear_cache")
async def cq_help_cmd_clear_cache(callback: CallbackQuery):
    """Handler for '/clear_cache' button from help menu."""
    if callback.from_user.id != ADMIN_USER_ID:
        await callback.answer("У вас нет прав на использование этой команды.", show_alert=True)
        return

    await callback.answer("Начинаю очистку кэша...")
    
    # Повторяем логику команды /clear_cache
    # clear_cache_command ожидает объект Message, callback.message подходит
    await clear_cache_command(callback.message)

@router.callback_query(F.data == "help_cmd_execute")
async def cq_help_cmd_execute(callback: CallbackQuery, state: FSMContext):
    """Handler for '/execute' button from help menu."""
    #if callback.from_user.id != ADMIN_USER_ID:
        #await callback.answer("У вас нет прав на использование этой команды.", show_alert=True)
        #return

    await callback.answer()
    # Повторяем логику команды /execute
    await state.set_state(Execution.code)
    await callback.message.answer(
        EXECUTE_HELP_TEXT,
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='markdown'
    )

@router.callback_query(F.data == "help_cmd_help")
async def cq_help_cmd_help(callback: CallbackQuery):
    """Handler for '/help' button from help menu. Edits the message."""
    try:
        # Пытаемся отредактировать сообщение, чтобы обновить его до актуального состояния
        await callback.message.edit_text(
            'Это бот для поиска примеров кода по библиотеке matplobblib.\n\n'
            'Нажмите на кнопку, чтобы выполнить команду:',
            reply_markup=kb.get_help_inline_keyboard(callback.from_user.id)
        )
        await callback.answer()
    except TelegramBadRequest as e:
        # Если сообщение не изменилось, Telegram выдаст ошибку.
        # Мы просто отвечаем на колбэк, чтобы убрать "часики" с кнопки.
        if "message is not modified" in e.message:
            await callback.answer("Вы уже в меню помощи.")
        else:
            # Перевыбрасываем другие, непредвиденные ошибки
            raise
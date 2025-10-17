# bot/handlers/github.py
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from aiogram.filters import  Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import aiohttp

import matplotlib
matplotlib.use('Agg') # Use a non-interactive backend for server environments
import os
import hashlib
from cachetools import TTLCache
import re
# ... прочие импорты
from .. import keyboards as kb, database
from .. import redis_client
from ..services import github_display # <-- обновим импорт на Шаге 2
from ..config import *

router = Router()

##################################################################################################
# MARKDOWN SEARCH & ABSTRACTS
##################################################################################################

class MarkdownSearch(StatesGroup):
    query = State()
    
class RepoManagement(StatesGroup):
    add_repo = State()
    edit_repo = State()
    choose_repo_for_search = State()
    choose_repo_for_browse = State()

# Cache for GitHub markdown search results to reduce API calls
github_search_cache = TTLCache(maxsize=100, ttl=600) # Cache search results for 10 minutes



@router.message(Command('lec_all'))
async def lec_all_command(message: Message, state: FSMContext):
    """Handles /lec_all, asking for a repo if multiple are configured."""
    user_id = message.from_user.id
    repos = await database.get_user_repos(user_id)

    if not repos:
        await message.answer("У вас не добавлено ни одного репозитория для просмотра. Пожалуйста, добавьте их в /settings.")
        return

    if len(repos) == 1:
        await github_display.display_lec_all_path(message, repo_path=repos[0], path="")
        return

    # Ask user to choose a repo
    builder = InlineKeyboardBuilder()
    for repo in repos:
        repo_hash = hashlib.sha1(repo.encode()).hexdigest()[:16]
        kb.code_path_cache[repo_hash] = repo
        builder.row(InlineKeyboardButton(text=repo, callback_data=f"lec_browse_repo:{repo_hash}"))

    await message.answer("Выберите репозиторий для просмотра:", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("lec_browse_repo:"))
async def cq_lec_browse_repo_selected(callback: CallbackQuery):
    """Handles the selection of a repository for browsing."""
    repo_hash = callback.data.split(":", 1)[1]
    repo_path = kb.code_path_cache.get(repo_hash)
    if not repo_path:
        await callback.answer("Информация о репозитории устарела.", show_alert=True)
        return
    
    await callback.answer(f"Загружаю {repo_path}...")
    await github_display.display_lec_all_path(callback.message, repo_path=repo_path, path="", is_edit=True)
    
@router.callback_query(F.data.startswith("abs_nav_hash:"))
async def cq_lec_all_navigate(callback: CallbackQuery):
    """Handles navigation through lec_all repo directories."""
    path_hash = callback.data.split(":", 1)[1]
    path = kb.code_path_cache.get(path_hash)

    if path is None: # Important to check for None, as "" is a valid path (root)
        await callback.answer("Информация о навигации устарела. Пожалуйста, начните с /lec_all.", show_alert=True)
        return

    await callback.answer()
    # The path from cache now includes the repo, e.g., "owner/repo/folder" or just "owner/repo"
    path_parts = path.split('/')
    repo_path = f"{path_parts[0]}/{path_parts[1]}"
    relative_path = "/".join(path_parts[2:])
    
    await github_display.display_lec_all_path(callback.message, repo_path=repo_path, path=relative_path, is_edit=True)

@router.callback_query(F.data.startswith("abs_show_hash:"))
async def cq_lec_all_show_file(callback: CallbackQuery):
    """Calls the helper to display a file from the lec_all repo."""
    path_hash = callback.data.split(":", 1)[1]
    file_path = kb.code_path_cache.get(path_hash)

    if not file_path:
        await callback.answer("Информация о файле устарела. Пожалуйста, обновите навигацию.", show_alert=True)
        return

    # Send a new temporary message to inform the user about processing.
    file_name = file_path.split('/')[-1]
    status_msg = await callback.message.answer(f"⏳ Обработка файла `{file_name}`...", parse_mode='markdown')
    await callback.answer() # Acknowledge the button press

    path_parts = file_path.split('/')
    repo_path = f"{path_parts[0]}/{path_parts[1]}"
    relative_path = "/".join(path_parts[2:])
    await github_display.display_github_file(callback.message, callback.from_user.id, repo_path, relative_path, status_msg_to_delete=status_msg)

async def get_md_search_results_keyboard(user_id: int, page: int = 0) -> InlineKeyboardMarkup | None:
    """Создает инлайн-клавиатуру для страницы результатов поиска по конспектам с пагинацией."""
    search_data = await redis_client.get_user_cache(user_id, 'md_search')
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


async def search_github_md(query: str, repo_path: str) -> list[dict] | None:
    """Searches for markdown files in a specific GitHub repository."""
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        logging.error("GITHUB_TOKEN environment variable not set. Markdown search is disabled.")
        return None
    
    search_query = f"{query} repo:{repo_path} extension:md"
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
    user_id = message.from_user.id
    repos = await database.get_user_repos(user_id)

    if not repos:
        await message.answer("У вас не добавлено ни одного репозитория для поиска. Пожалуйста, добавьте их в /settings.")
        return

    if len(repos) == 1:
        await state.update_data(repo_to_search=repos[0])
        await state.set_state(MarkdownSearch.query)
        await message.answer(f"Введите запрос для поиска по репозиторию `{repos[0]}`:", parse_mode='markdown', reply_markup=ReplyKeyboardRemove())
        return

    # Ask user to choose a repo
    builder = InlineKeyboardBuilder()
    for repo in repos:
        repo_hash = hashlib.sha1(repo.encode()).hexdigest()[:16]
        kb.code_path_cache[repo_hash] = repo
        builder.row(InlineKeyboardButton(text=repo, callback_data=f"lec_search_repo:{repo_hash}"))

    await state.set_state(RepoManagement.choose_repo_for_search)
    await message.answer("Выберите репозиторий для поиска:", reply_markup=builder.as_markup())

@router.callback_query(RepoManagement.choose_repo_for_search, F.data.startswith("lec_search_repo:"))
async def cq_lec_search_repo_selected(callback: CallbackQuery, state: FSMContext):
    repo_hash = callback.data.split(":", 1)[1]
    repo_path = kb.code_path_cache.get(repo_hash)
    if not repo_path:
        await callback.answer("Информация о репозитории устарела.", show_alert=True)
        return

    await state.update_data(repo_to_search=repo_path)
    await state.set_state(MarkdownSearch.query)
    await callback.message.edit_text(f"Введите запрос для поиска по репозиторию `{repo_path}`:", parse_mode='markdown')
    await callback.answer()

@router.message(MarkdownSearch.query)
async def process_md_search_query(message: Message, state: FSMContext):
    """Processes the user's query for markdown files."""
    user_data = await state.get_data()
    repo_to_search = user_data.get('repo_to_search')
    await state.clear()
    query = message.text
    status_msg = await message.answer(f"Идет поиск по запросу '{query}' в репозитории `{repo_to_search}`...", parse_mode='markdown')
    results = await search_github_md(query, repo_to_search)

    if results is None:
        await status_msg.edit_text("Произошла ошибка при поиске. Попробуйте позже.")
        await message.answer("Выберите следующую команду:", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))
        return

    if not results:
        await status_msg.edit_text(f"По вашему запросу '{query}' ничего не найдено.")
        await message.answer("Выберите следующую команду:", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))
        return

    user_id = message.from_user.id
    await redis_client.set_user_cache(user_id, 'md_search', {'query': query, 'results': results, 'repo_path': repo_to_search})

    keyboard = await get_md_search_results_keyboard(user_id, page=0)
    total_pages = (len(results) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE

    await status_msg.edit_text(
        f"Найдено {len(results)} файлов в `{repo_to_search}` по запросу '{query}'.\nСтраница 1/{total_pages}:",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("md_search_page:"))
async def cq_md_search_pagination(callback: CallbackQuery):
    """Обрабатывает нажатия на кнопки пагинации в результатах поиска по конспектам."""
    user_id = callback.from_user.id
    search_data = await redis_client.get_user_cache(user_id, 'md_search')
    if not search_data:
        await callback.answer("Результаты поиска устарели. Пожалуйста, выполните поиск заново.", show_alert=True)
        await callback.message.delete()
        return

    page = int(callback.data.split(":", 1)[1])
    keyboard = await get_md_search_results_keyboard(user_id, page=page)
    
    results = search_data['results']
    query = search_data['query']
    repo_path = search_data['repo_path']
    total_pages = (len(results) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE

    try:
        await callback.message.edit_text(
            f"Найдено {len(results)} файлов в `{repo_path}` по запросу '{query}'.\nСтраница {page + 1}/{total_pages}:",
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
    relative_path = kb.code_path_cache.get(path_hash)
    search_data = await redis_client.get_user_cache(callback.from_user.id, 'md_search')

    if not relative_path or not search_data:
        await callback.answer("Информация о файле устарела. Пожалуйста, выполните поиск заново.", show_alert=True)
        return
    
    # Send a new temporary message to inform the user about processing.
    file_name = relative_path.split('/')[-1]
    status_msg = await callback.message.answer(f"⏳ Обработка файла `{file_name}`...", parse_mode='markdown')
    await callback.answer() # Acknowledge the button press

    repo_path = search_data['repo_path']
    await github_display.display_github_file(callback.message, callback.from_user.id, repo_path, relative_path, status_msg_to_delete=status_msg)


##################################################################################################
# REPO MANAGEMENT
##################################################################################################

@router.callback_query(F.data == "manage_repos")
async def cq_manage_repos(callback: CallbackQuery):
    """Displays the repository management interface."""
    user_id = callback.from_user.id
    keyboard = await kb.get_repo_management_keyboard(user_id)
    await callback.message.edit_text("Управление вашими репозиториями GitHub:", reply_markup=keyboard)
    await callback.answer()



@router.callback_query(F.data == "repo_add_new")
async def cq_add_new_repo_prompt(callback: CallbackQuery, state: FSMContext):
    """Prompts the user to enter a new repository path."""
    await state.set_state(RepoManagement.add_repo)
    await callback.message.edit_text("Отправьте репозиторий в формате `owner/repository`:", reply_markup=None)
    await callback.answer()

@router.message(RepoManagement.add_repo)
async def process_add_repo(message: Message, state: FSMContext):
    """Processes the new repository path from the user."""
    repo_path = message.text.strip()
    # Basic validation
    if re.match(r"^[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+$", repo_path):
        success = await database.add_user_repo(message.from_user.id, repo_path)
        if success:
            await message.answer(f"✅ Репозиторий `{repo_path}` успешно добавлен.", parse_mode='markdown')
        else:
            await message.answer(f"⚠️ Репозиторий `{repo_path}` уже есть в вашем списке.", parse_mode='markdown')
    else:
        await message.answer("❌ Неверный формат. Пожалуйста, используйте формат `owner/repository`.")

    await state.clear()
    # Show updated repo list
    keyboard = await kb.get_repo_management_keyboard(message.from_user.id)
    await message.answer("Управление вашими репозиториями GitHub:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("repo_del_hash:"))
async def cq_delete_repo(callback: CallbackQuery):
    """Deletes a repository from the user's list."""
    repo_hash = callback.data.split(":", 1)[1]
    repo_path = kb.code_path_cache.get(repo_hash)
    if not repo_path:
        await callback.answer("Информация о репозитории устарела.", show_alert=True)
        return

    await database.remove_user_repo(callback.from_user.id, repo_path)
    await callback.answer(f"Репозиторий {repo_path} удален.", show_alert=False)

    # Refresh the keyboard
    keyboard = await kb.get_repo_management_keyboard(callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=keyboard)

@router.callback_query(F.data.startswith("repo_edit_hash:"))
async def cq_edit_repo_prompt(callback: CallbackQuery, state: FSMContext):
    """Prompts the user to edit a repository path."""
    repo_hash = callback.data.split(":", 1)[1]
    repo_path = kb.code_path_cache.get(repo_hash)
    if not repo_path:
        await callback.answer("Информация о репозитории устарела.", show_alert=True)
        return

    await state.set_state(RepoManagement.edit_repo)
    await state.update_data(old_repo_path=repo_path)
    await callback.message.edit_text(f"Отправьте новое имя для репозитория `{repo_path}` (в формате `owner/repo`):", parse_mode='markdown')
    await callback.answer()

@router.message(RepoManagement.edit_repo)
async def process_edit_repo(message: Message, state: FSMContext):
    """Processes the edited repository path."""
    new_repo_path = message.text.strip()
    user_data = await state.get_data()
    old_repo_path = user_data.get('old_repo_path')

    if re.match(r"^[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+$", new_repo_path):
        await database.update_user_repo(message.from_user.id, old_repo_path, new_repo_path)
        await message.answer(f"✅ Репозиторий обновлен на `{new_repo_path}`.", parse_mode='markdown')
    else:
        await message.answer("❌ Неверный формат. Пожалуйста, используйте формат `owner/repository`.")

    await state.clear()
    # Show updated repo list
    keyboard = await kb.get_repo_management_keyboard(message.from_user.id)
    await message.answer("Управление вашими репозиториями GitHub:", reply_markup=keyboard)
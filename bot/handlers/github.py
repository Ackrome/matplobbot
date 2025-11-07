# bot/handlers/github.py
import logging
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from aiogram.filters import  Command, StateFilter
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import aiohttp
import os
import hashlib
from cachetools import TTLCache
import re

from .. import keyboards as kb, database
from shared_lib.redis_client import redis_client
from ..services import github_display
from ..config import *
from shared_lib.i18n import translator

router = Router()

class MarkdownSearch(StatesGroup):
    query = State()
    
class RepoManagement(StatesGroup):
    add_repo = State()
    edit_repo = State()
    choose_repo_for_search = State()
    choose_repo_for_browse = State()

# Cache for GitHub markdown search results to reduce API calls
github_search_cache = TTLCache(maxsize=100, ttl=600) # Cache search results for 10 minutes

class GitHubManager:
    def __init__(self):
        self.router = Router()
        self._register_handlers()

    def _register_handlers(self):
        # Browse
        self.router.message(Command('lec_all'))(self.lec_all_command)
        self.router.callback_query(F.data.startswith("lec_browse_repo:"))(self.cq_lec_browse_repo_selected)
        self.router.callback_query(F.data.startswith("abs_nav_hash:"))(self.cq_lec_all_navigate)
        self.router.callback_query(F.data.startswith("abs_show_hash:"))(self.cq_lec_all_show_file)
        # Search
        self.router.message(Command('lec_search'))(self.lec_search_command)
        self.router.callback_query(RepoManagement.choose_repo_for_search, F.data.startswith("lec_search_repo:"))(self.cq_lec_search_repo_selected)
        self.router.message(MarkdownSearch.query)(self.process_md_search_query)
        self.router.callback_query(F.data.startswith("md_search_page:"))(self.cq_md_search_pagination)
        self.router.callback_query(F.data.startswith("show_md_hash:"))(self.cq_show_md_result)
        # Repo Management
        self.router.callback_query(F.data == "manage_repos")(self.cq_manage_repos)
        self.router.callback_query(F.data == "repo_add_new")(self.cq_add_new_repo_prompt)
        self.router.message(RepoManagement.add_repo)(self.process_add_repo)
        self.router.callback_query(F.data.startswith("repo_del_hash:"))(self.cq_delete_repo)
        self.router.callback_query(F.data.startswith("repo_edit_hash:"))(self.cq_edit_repo_prompt)
        self.router.message(RepoManagement.edit_repo)(self.process_edit_repo)

    # --- Browse Handlers ---

    async def lec_all_command(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        lang = await translator.get_language(user_id, message.chat.id)
        repos = await database.get_user_repos(user_id)

        if not repos:
            await message.answer(translator.gettext(lang, "github_no_repos_configured"))
            return

        if len(repos) == 1:
            await github_display.display_lec_all_path(message, repo_path=repos[0], path="")
            return

        builder = InlineKeyboardBuilder()
        for repo in repos:
            repo_hash = hashlib.sha1(repo.encode()).hexdigest()[:16]
            kb.code_path_cache[repo_hash] = repo
            builder.row(InlineKeyboardButton(text=repo, callback_data=f"lec_browse_repo:{repo_hash}"))

        await message.answer(translator.gettext(lang, "github_choose_repo_browse"), reply_markup=builder.as_markup())

    async def cq_lec_browse_repo_selected(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id, callback.message.chat.id)
        repo_hash = callback.data.split(":", 1)[1]
        repo_path = kb.code_path_cache.get(repo_hash)
        if not repo_path:
            await callback.answer(translator.gettext(lang, "github_info_outdated"), show_alert=True)
            return
        
        await callback.answer(translator.gettext(lang, "github_loading_repo", repo_path=repo_path))
        await github_display.display_lec_all_path(callback.message, repo_path=repo_path, path="", is_edit=True, user_id=user_id)
        
    async def cq_lec_all_navigate(self, callback: CallbackQuery):
        path_hash = callback.data.split(":", 1)[1]
        path = kb.code_path_cache.get(path_hash)
        lang = await translator.get_language(callback.from_user.id, callback.message.chat.id)

        if path is None:
            await callback.answer(translator.gettext(lang, "matp_all_show_error"), show_alert=True)
            return

        await callback.answer()
        path_parts = path.split('/')
        repo_path = f"{path_parts[0]}/{path_parts[1]}"
        relative_path = "/".join(path_parts[2:])
        
        await github_display.display_lec_all_path(callback.message, repo_path=repo_path, path=relative_path, is_edit=True, user_id=callback.from_user.id)

    async def cq_lec_all_show_file(self, callback: CallbackQuery):
        path_hash = callback.data.split(":", 1)[1]
        file_path = kb.code_path_cache.get(path_hash)
        lang = await translator.get_language(callback.from_user.id, callback.message.chat.id)
        if not file_path:
            await callback.answer(translator.gettext(lang, "github_file_info_outdated"), show_alert=True)
            return

        file_name = file_path.split('/')[-1]
        status_msg = await callback.message.answer(translator.gettext(lang, "github_processing_file", file_name=file_name), parse_mode='markdown')
        await callback.answer()

        path_parts = file_path.split('/')
        repo_path = f"{path_parts[0]}/{path_parts[1]}"
        relative_path = "/".join(path_parts[2:])
        await github_display.display_github_file(callback.message, callback.from_user.id, repo_path, relative_path, status_msg_to_delete=status_msg)

    # --- Search Handlers ---

    async def _get_md_search_results_keyboard(self, user_id: int, page: int = 0) -> InlineKeyboardMarkup | None:
        search_data = await redis_client.get_user_cache(user_id, 'md_search')
        if not search_data or not search_data.get('results'):
            return None

        results = search_data['results']
        builder = InlineKeyboardBuilder()
        
        start = page * SEARCH_RESULTS_PER_PAGE
        end = start + SEARCH_RESULTS_PER_PAGE
        page_items = results[start:end]

        for item in page_items:
            path_hash = hashlib.sha1(item['path'].encode()).hexdigest()[:16]
            kb.code_path_cache[path_hash] = item['path']
            builder.row(InlineKeyboardButton(text=f"📄 {item['path']}", callback_data=f"show_md_hash:{path_hash}"))

        total_pages = (len(results) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE
        if total_pages > 1:
            pagination_buttons = []
            lang = await translator.get_language(user_id)
            if page > 0:
                pagination_buttons.append(InlineKeyboardButton(text=translator.gettext(lang, "pagination_back"), callback_data=f"md_search_page:{page - 1}"))
            pagination_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
            if end < len(results):
                pagination_buttons.append(InlineKeyboardButton(text=translator.gettext(lang, "pagination_forward"), callback_data=f"md_search_page:{page + 1}"))
            builder.row(*pagination_buttons)

        return builder.as_markup()

    async def _search_github_md(self, query: str, repo_path: str) -> list[dict] | None:
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            logging.error("GITHUB_TOKEN environment variable not set. Markdown search is disabled.")
            return None
        
        search_query = f"{query} repo:{repo_path} extension:md"
        url = "https://api.github.com/search/code"
        headers = {"Accept": "application/vnd.github.v3+json", "X-GitHub-Api-Version": "2022-11-28", "Authorization": f"Bearer {github_token}"}
        params = {"q": search_query, "per_page": 100}

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("items", [])
                        github_search_cache[query] = results
                        return results
                    else:
                        logging.error(f"GitHub API search failed with status {response.status}: {await response.text()}")
                        return None
        except Exception as e:
            logging.error(f"Error during GitHub API request: {e}", exc_info=True)
            return None

    async def lec_search_command(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        lang = await translator.get_language(user_id, message.chat.id)
        repos = await database.get_user_repos(user_id)

        if not repos:
            await message.answer(translator.gettext(lang, "github_no_repos_configured"))
            return

        if len(repos) == 1:
            await state.update_data(repo_to_search=repos[0])
            await state.set_state(MarkdownSearch.query)
            await message.answer(translator.gettext(lang, "github_search_prompt", repo_path=repos[0]), parse_mode='markdown', reply_markup=ReplyKeyboardRemove())
            return

        builder = InlineKeyboardBuilder()
        for repo in repos:
            repo_hash = hashlib.sha1(repo.encode()).hexdigest()[:16]
            kb.code_path_cache[repo_hash] = repo
            builder.row(InlineKeyboardButton(text=repo, callback_data=f"lec_search_repo:{repo_hash}"))

        await state.set_state(RepoManagement.choose_repo_for_search)
        await message.answer(translator.gettext(lang, "github_choose_repo_search"), reply_markup=builder.as_markup())

    async def cq_lec_search_repo_selected(self, callback: CallbackQuery, state: FSMContext):
        lang = await translator.get_language(callback.from_user.id, callback.message.chat.id)
        repo_hash = callback.data.split(":", 1)[1]
        repo_path = kb.code_path_cache.get(repo_hash)
        if not repo_path:
            await callback.answer(translator.gettext(lang, "github_info_outdated"), show_alert=True)
            return

        await state.update_data(repo_to_search=repo_path)
        await state.set_state(MarkdownSearch.query)
        await callback.message.edit_text(translator.gettext(lang, "github_search_prompt", repo_path=repo_path), parse_mode='markdown')
        await callback.answer()

    async def _handle_md_search_success(self, status_msg: Message, user_id: int, query: str, repo_to_search: str, results: list):
        lang = await translator.get_language(user_id)
        await redis_client.set_user_cache(user_id, 'md_search', {'query': query, 'results': results, 'repo_path': repo_to_search})
        keyboard = await self._get_md_search_results_keyboard(user_id, page=0)
        total_pages = (len(results) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE
        await status_msg.edit_text(
            translator.gettext(lang, "github_search_results_found", count=len(results), repo_path=repo_to_search, query=query, page=1, total_pages=total_pages),
            reply_markup=keyboard
        )

    async def process_md_search_query(self, message: Message, state: FSMContext):
        user_data = await state.get_data()
        repo_to_search = user_data.get('repo_to_search')
        user_id = message.from_user.id
        lang = await translator.get_language(user_id, message.chat.id)
        await state.clear()
        query = message.text
        status_msg = await message.answer(translator.gettext(lang, "github_search_in_progress", query=query, repo_path=repo_to_search), parse_mode='markdown')
        
        results = await self._search_github_md(query, repo_to_search)

        if results is None:
            await status_msg.edit_text(translator.gettext(lang, "github_search_error"))
        elif not results:
            await status_msg.edit_text(translator.gettext(lang, "github_search_no_results", query=query))
        else:
            await self._handle_md_search_success(status_msg, user_id, query, repo_to_search, results)
            return # Success, no need for final message

        await message.answer(translator.gettext(lang, "choose_next_command"), reply_markup=await kb.get_main_reply_keyboard(user_id))

    async def cq_md_search_pagination(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id, callback.message.chat.id)
        search_data = await redis_client.get_user_cache(user_id, 'md_search')
        if not search_data:
            await callback.answer(translator.gettext(lang, "search_results_outdated"), show_alert=True)
            await callback.message.delete()
            return

        page = int(callback.data.split(":", 1)[1])
        keyboard = await self._get_md_search_results_keyboard(user_id, page=page)
        
        results, query, repo_path = search_data['results'], search_data['query'], search_data['repo_path']
        total_pages = (len(results) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE

        try:
            await callback.message.edit_text(
                translator.gettext(lang, "github_search_results_found", count=len(results), repo_path=repo_path, query=query, page=page + 1, total_pages=total_pages),
                reply_markup=keyboard
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in e.message: raise
        finally:
            await callback.answer()

    async def cq_show_md_result(self, callback: CallbackQuery):
        path_hash = callback.data.split(":", 1)[1]
        lang = await translator.get_language(callback.from_user.id, callback.message.chat.id)
        relative_path = kb.code_path_cache.get(path_hash)
        search_data = await redis_client.get_user_cache(callback.from_user.id, 'md_search')

        if not relative_path or not search_data:
            await callback.answer(translator.gettext(lang, "search_results_outdated"), show_alert=True)
            return
        
        file_name = relative_path.split('/')[-1]
        status_msg = await callback.message.answer(translator.gettext(lang, "github_processing_file", file_name=file_name), parse_mode='markdown')
        await callback.answer()

        repo_path = search_data['repo_path']
        await github_display.display_github_file(callback.message, callback.from_user.id, repo_path, relative_path, status_msg_to_delete=status_msg)

    # --- Repo Management Handlers ---

    async def _show_repo_management_menu(self, message: Message, user_id: int, state: FSMContext, is_edit: bool = False):
        """Helper to display the repo management menu."""
        lang = await translator.get_language(user_id, message.chat.id)
        keyboard = await kb.get_repo_management_keyboard(user_id, state, message.chat.id)
        text = translator.gettext(lang, "repo_management_header")
        if is_edit:
            try:
                await message.edit_text(text, reply_markup=keyboard)
            except TelegramBadRequest as e:
                logger.warning(f"Failed to edit message in _show_repo_management_menu: {e}")
                # Fallback to sending a new message if editing fails
                await message.answer(text, reply_markup=keyboard)
        else:
            await message.answer(text, reply_markup=keyboard)

    async def cq_manage_repos(self, callback: CallbackQuery, state: FSMContext):
        await callback.answer() # Acknowledge the callback immediately
        await self._show_repo_management_menu(callback.message, callback.from_user.id, state, is_edit=True)

    async def cq_add_new_repo_prompt(self, callback: CallbackQuery, state: FSMContext):
        lang = await translator.get_language(callback.from_user.id, callback.message.chat.id)
        await state.set_state(RepoManagement.add_repo)
        await callback.message.edit_text(translator.gettext(lang, "repo_add_new_prompt"), reply_markup=None)
        await callback.answer()

    async def process_add_repo(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        lang = await translator.get_language(user_id, message.chat.id)
        repo_path = message.text.strip()

        if re.match(r"^[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+$", repo_path):
            success = await database.add_user_repo(user_id, repo_path)
            await message.answer(translator.gettext(lang, "repo_add_success" if success else "repo_add_already_exists", repo_path=repo_path), parse_mode='markdown')
        else:
            await message.answer(translator.gettext(lang, "repo_add_invalid_format"))

        await state.clear()
        await self._show_repo_management_menu(message, user_id, state)

    async def cq_delete_repo(self, callback: CallbackQuery, state: FSMContext):
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id, callback.message.chat.id)
        repo_hash = callback.data.split(":", 1)[1]
        repo_path = kb.code_path_cache.get(repo_hash)
        if not repo_path:
            await callback.answer(translator.gettext(lang, "github_info_outdated"), show_alert=True)
            return

        await database.remove_user_repo(user_id, repo_path)
        await callback.answer(translator.gettext(lang, "repo_deleted", repo_path=repo_path), show_alert=False)
        await self._show_repo_management_menu(callback.message, user_id, state, is_edit=True)

    async def cq_edit_repo_prompt(self, callback: CallbackQuery, state: FSMContext):
        repo_hash = callback.data.split(":", 1)[1]
        repo_path = kb.code_path_cache.get(repo_hash)
        lang = await translator.get_language(callback.from_user.id, callback.message.chat.id)
        if not repo_path:
            await callback.answer(translator.gettext(lang, "github_info_outdated"), show_alert=True)
            return

        await state.set_state(RepoManagement.edit_repo)
        await state.update_data(old_repo_path=repo_path)
        await callback.message.edit_text(translator.gettext(lang, "repo_edit_prompt", old_repo_path=repo_path), parse_mode='markdown')
        await callback.answer()

    async def process_edit_repo(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        lang = await translator.get_language(user_id, message.chat.id)
        new_repo_path = message.text.strip()
        user_data = await state.get_data()
        old_repo_path = user_data.get('old_repo_path')

        if re.match(r"^[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+$", new_repo_path):
            await database.update_user_repo(user_id, old_repo_path, new_repo_path)
            await message.answer(translator.gettext(lang, "repo_updated", new_repo_path=new_repo_path), parse_mode='markdown')
        else:
            await message.answer(translator.gettext(lang, "repo_add_invalid_format"))

        await state.clear()
        await self._show_repo_management_menu(message, user_id, state)
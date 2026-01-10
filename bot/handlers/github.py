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
import asyncio

from .. import keyboards as kb, database
from shared_lib.redis_client import redis_client
from ..services import github_display
from ..config import *
from ..services.repo_indexer import index_github_repository
from shared_lib.services.semantic_search import search_engine
from shared_lib.i18n import translator
from shared_lib.services.llm_service import llm_service

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
        self.router.callback_query(F.data.startswith("repo_index_hash:"))(self.cq_index_repo)
        # RAG
        self.router.message(Command('ask'))(self.ask_command)

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
        query = message.text
        
        status_msg = await message.answer(f"🔍 Ищу '{query}' в `{repo_to_search}` (нейропоиск)...", parse_mode='Markdown')
        
        # Используем наш векторный движок
        # source_type = "repo:owner/name"
        search_key = f"repo:{repo_to_search}"
        
        results = await search_engine.search(query, source_type=search_key, top_k=10)
        
        if not results:
            # Fallback на старый поиск через GitHub API, если векторы не дали результата (или база пуста)
            # await self._search_github_md(query, repo_to_search) # Старый метод
            await status_msg.edit_text("По вашему запросу ничего не найдено (векторный поиск).")
            return

        # Формируем результаты для кэша и клавиатуры
        # Нам нужно адаптировать формат результатов под то, что ждет _get_md_search_results_keyboard
        # Ожидается список dict c ключом 'path'
        
        formatted_results = []
        seen_files = set()
        
        for r in results:
            # r['path'] выглядит как "folder/file.md#chunk_0"
            # Нам для открытия файла нужен чистый путь
            file_path = r['metadata']['file_path']
            
            # Дедупликация: если нашли 5 чанков из одного файла, показываем файл один раз
            # (Или можно показывать с якорями, если реализуешь навигацию по чанкам)
            if file_path not in seen_files:
                formatted_results.append({'path': file_path, 'score': r['score']})
                seen_files.add(file_path)

        await self._handle_md_search_success(status_msg, user_id, query, repo_to_search, formatted_results)



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
    
    async def cq_index_repo(self, callback: CallbackQuery):
        repo_hash = callback.data.split(":", 1)[1]
        repo_path = kb.code_path_cache.get(repo_hash)
        
        if not repo_path:
            await callback.answer("Ошибка: данные устарели", show_alert=True)
            return

        await callback.answer("Запущена индексация... Я сообщу по завершении.")
        
        # Запускаем в фоне
        asyncio.create_task(self._run_indexing_task(callback.message, repo_path))

    async def _run_indexing_task(self, message: Message, repo_path: str):
        status_msg = await message.answer(f"⏳ Индексация `{repo_path}` началась...", parse_mode='Markdown')
        try:
            await index_github_repository(repo_path)
            await status_msg.edit_text(f"✅ Индексация `{repo_path}` завершена! Теперь поиск работает по смыслу.", parse_mode='Markdown')
        except Exception as e:
            await status_msg.edit_text(f"❌ Ошибка индексации: {e}")
            
    async def ask_command(self, message: Message):
        """
        Hybrid RAG Handler: /ask [query]
        """
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply("⚠️ Usage: `/ask <your question>`\nExample: `/ask What is Gini?`", parse_mode='Markdown')
            return
        
        query = args[1]
        user_id = message.from_user.id
        
        # 1. Get User Repos
        repos = await database.get_user_repos(user_id)
        if not repos:
            await message.reply("Please add a GitHub repository in /settings first.")
            return

        status_msg = await message.answer("🧠 **Thinking...**\n1. Searching notes (Hybrid)...", parse_mode='Markdown')
        
        # 2. Search (Hybrid)
        # We search the first repo for now. 
        # TODO: Support searching multiple repos (requires loop or generic source_type)
        target_repo = repos[0] 
        search_key = f"repo:{target_repo}"
        
        # --- OPTIMIZATION 3: Reduce top_k to 2 ---
        # This drastically reduces the token count sent to the LLM.
        results = await search_engine.search(query, source_type=search_key, top_k=2)
        
        if not results:
            await status_msg.edit_text(f"❌ I searched `{target_repo}` but found nothing relevant for '**{query}**'.", parse_mode='Markdown')
            return

        # 3. Generate
        await status_msg.edit_text(f"🧠 **Thinking...**\n1. Found {len(results)} relevant notes.\n2. Reading & Generating answer...", parse_mode='Markdown')
        await message.bot.send_chat_action(message.chat.id, "typing")
        
        context_texts = [r['content'] for r in results]
        answer = await llm_service.generate_answer(query, context_texts)
        
        # 4. Format Output
        # Extract filenames for citation
        sources = set()
        for r in results:
            path = r['metadata'].get('file_path', 'unknown')
            score = r.get('score', 0.0)
            sources.add(f"`{path}` (match: {score:.2f})")
            
        sources_text = "\n\n📚 **Sources:**\n" + "\n".join(sources)
        final_response = f"{answer}{sources_text}"
        
        await status_msg.edit_text(final_response, parse_mode='Markdown')
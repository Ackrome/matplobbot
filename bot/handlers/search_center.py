import hashlib
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from shared_lib.i18n import translator
from shared_lib.redis_client import redis_client

from .. import database
from .. import keyboards as kb
from ..config import SEARCH_RESULTS_PER_PAGE
from ..services import github_display, library_display
from ..services.search_center import (
    GLOBAL_SOURCE_GITHUB,
    GLOBAL_SOURCE_LIBRARY,
    SEARCH_KIND_GITHUB,
    SEARCH_KIND_GLOBAL,
    SEARCH_KIND_LIBRARY,
    SEARCH_KIND_SCHEDULE,
    build_default_global_filters,
    format_global_result_label,
    normalize_global_filters,
    search_global_sources,
    search_library_examples,
    search_repository_markdown,
    toggle_global_repo,
    toggle_global_source,
)
from .github import GitHubManager
from .library import LibraryManager
from .schedule import ScheduleManager

logger = logging.getLogger(__name__)


class SearchCenterStates(StatesGroup):
    awaiting_global_query = State()
    awaiting_preset_name = State()


class SearchCenterManager:
    def __init__(
        self,
        library_manager: LibraryManager,
        github_manager: GitHubManager,
        schedule_manager: ScheduleManager,
    ):
        self.router = Router()
        self.library_manager = library_manager
        self.github_manager = github_manager
        self.schedule_manager = schedule_manager
        self._register_handlers()

    def _register_handlers(self):
        self.router.message(Command("search"))(self.command_global_search)
        self.router.message(Command("search_presets"))(self.command_search_presets)
        self.router.message(SearchCenterStates.awaiting_global_query)(self.process_global_query)
        self.router.message(SearchCenterStates.awaiting_preset_name)(self.process_preset_name)

        self.router.callback_query(F.data.startswith("global_toggle_source:"))(
            self.cq_toggle_global_source
        )
        self.router.callback_query(F.data.startswith("global_toggle_repo:"))(
            self.cq_toggle_global_repo
        )
        self.router.callback_query(F.data.startswith("global_page:"))(self.cq_global_page)
        self.router.callback_query(F.data.startswith("show_global_idx:"))(
            self.cq_show_global_result
        )

        self.router.callback_query(F.data.startswith("search_preset_save:"))(
            self.cq_save_search_preset
        )
        self.router.callback_query(F.data.startswith("search_preset_run:"))(
            self.cq_run_search_preset
        )
        self.router.callback_query(F.data.startswith("search_preset_delete:"))(
            self.cq_delete_search_preset
        )

    async def command_global_search(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        repo_paths = await database.get_user_repos(user_id)
        context = {
            "query": "",
            "filters": build_default_global_filters(repo_paths),
            "results": [],
        }
        await redis_client.set_user_cache(user_id, "global_search", context)
        await state.set_state(SearchCenterStates.awaiting_global_query)
        await self._render_global_search_message(message, user_id, is_edit=False, page=0)

    async def process_global_query(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        lang = await translator.get_language(user_id, message.chat.id)
        query = (message.text or "").strip()

        if not query:
            await message.answer(translator.gettext(lang, "global_search_empty_query"))
            return

        await state.clear()
        await self._run_global_search(message, user_id, query=query, status_message=None)

    async def _run_global_search(
        self,
        message: Message,
        user_id: int,
        query: str,
        filters: dict | None = None,
        status_message: Message | None = None,
    ):
        lang = await translator.get_language(user_id, message.chat.id)
        repo_paths = await database.get_user_repos(user_id)
        current_context = await redis_client.get_user_cache(user_id, "global_search") or {}
        active_filters = normalize_global_filters(filters or current_context.get("filters"), repo_paths)

        working_message = status_message or await message.answer(
            translator.gettext(lang, "search_in_progress", query=query)
        )
        results, normalized_filters = await search_global_sources(
            query, active_filters, repo_paths, limit=20
        )

        await redis_client.set_user_cache(
            user_id,
            "global_search",
            {"query": query, "filters": normalized_filters, "results": results},
        )
        keyboard = await self._build_global_search_keyboard(user_id, page=0)
        text = await self._build_global_search_text(user_id, page=0)
        await working_message.edit_text(text, reply_markup=keyboard)

    async def _build_global_search_text(self, user_id: int, page: int = 0) -> str:
        context = await redis_client.get_user_cache(user_id, "global_search") or {}
        lang = await translator.get_language(user_id)
        query = context.get("query", "")
        results = context.get("results") or []
        filters = context.get("filters") or {}
        filters_text = self._format_global_filters_summary(lang, filters)

        if not query:
            return translator.gettext(lang, "global_search_prompt", filters=filters_text)

        if not results:
            return translator.gettext(lang, "global_search_no_results", query=query, filters=filters_text)

        total_pages = (len(results) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE
        safe_page = min(page, max(total_pages - 1, 0))
        return translator.gettext(
            lang,
            "global_search_results_found",
            count=len(results),
            query=query,
            page=safe_page + 1,
            total_pages=total_pages,
            filters=filters_text,
        )

    def _format_global_filters_summary(self, lang: str, filters: dict) -> str:
        sources = filters.get("sources") or []
        selected_repos = filters.get("repo_paths") or []
        source_labels = []

        if GLOBAL_SOURCE_LIBRARY in sources:
            source_labels.append(translator.gettext(lang, "global_search_source_library"))
        if GLOBAL_SOURCE_GITHUB in sources:
            github_label = translator.gettext(lang, "global_search_source_github")
            if selected_repos:
                github_label = f"{github_label} ({', '.join(selected_repos)})"
            source_labels.append(github_label)

        summary = ", ".join(source_labels) if source_labels else "-"
        return translator.gettext(lang, "global_search_filters", filters=summary)

    async def _build_global_search_keyboard(
        self, user_id: int, page: int = 0
    ) -> InlineKeyboardMarkup | None:
        context = await redis_client.get_user_cache(user_id, "global_search")
        if not context:
            return None

        lang = await translator.get_language(user_id)
        repo_paths = await database.get_user_repos(user_id)
        filters = normalize_global_filters(context.get("filters"), repo_paths)
        results = context.get("results") or []
        query = context.get("query", "")

        builder = InlineKeyboardBuilder()

        if results:
            start = page * SEARCH_RESULTS_PER_PAGE
            end = start + SEARCH_RESULTS_PER_PAGE
            for offset, result in enumerate(results[start:end]):
                global_index = start + offset
                builder.row(
                    InlineKeyboardButton(
                        text=format_global_result_label(result),
                        callback_data=f"show_global_idx:{global_index}",
                    )
                )

            total_pages = (len(results) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE
            if total_pages > 1:
                pagination_buttons = []
                if page > 0:
                    pagination_buttons.append(
                        InlineKeyboardButton(
                            text=translator.gettext(lang, "pagination_back"),
                            callback_data=f"global_page:{page - 1}",
                        )
                    )
                pagination_buttons.append(
                    InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")
                )
                if end < len(results):
                    pagination_buttons.append(
                        InlineKeyboardButton(
                            text=translator.gettext(lang, "pagination_forward"),
                            callback_data=f"global_page:{page + 1}",
                        )
                    )
                builder.row(*pagination_buttons)

        library_enabled = GLOBAL_SOURCE_LIBRARY in filters["sources"]
        builder.row(
            InlineKeyboardButton(
                text=f"{'✅' if library_enabled else '❌'} {translator.gettext(lang, 'global_search_source_library')}",
                callback_data=f"global_toggle_source:{GLOBAL_SOURCE_LIBRARY}",
            )
        )

        if repo_paths:
            github_enabled = GLOBAL_SOURCE_GITHUB in filters["sources"]
            builder.row(
                InlineKeyboardButton(
                    text=f"{'✅' if github_enabled else '❌'} {translator.gettext(lang, 'global_search_source_github')}",
                    callback_data=f"global_toggle_source:{GLOBAL_SOURCE_GITHUB}",
                )
            )

            if github_enabled:
                for repo_path in repo_paths:
                    repo_hash = hashlib.sha1(repo_path.encode()).hexdigest()[:16]
                    kb.code_path_cache[repo_hash] = repo_path
                    builder.row(
                        InlineKeyboardButton(
                            text=f"{'✅' if repo_path in filters['repo_paths'] else '❌'} {repo_path}",
                            callback_data=f"global_toggle_repo:{repo_hash}",
                        )
                    )

        if query:
            builder.row(
                InlineKeyboardButton(
                    text=translator.gettext(lang, "search_preset_save_button"),
                    callback_data=f"search_preset_save:{SEARCH_KIND_GLOBAL}",
                )
            )

        return builder.as_markup()

    async def _render_global_search_message(
        self, message: Message, user_id: int, is_edit: bool = False, page: int = 0
    ):
        keyboard = await self._build_global_search_keyboard(user_id, page=page)
        text = await self._build_global_search_text(user_id, page=page)
        if is_edit:
            await message.edit_text(text, reply_markup=keyboard)
        else:
            await message.answer(text, reply_markup=keyboard)

    async def cq_toggle_global_source(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id, callback.message.chat.id)
        source = callback.data.split(":", 1)[1]
        context = await redis_client.get_user_cache(user_id, "global_search")
        if not context:
            await callback.answer(
                translator.gettext(lang, "search_preset_missing_context"), show_alert=True
            )
            return

        repo_paths = await database.get_user_repos(user_id)
        updated_filters, changed = toggle_global_source(context.get("filters") or {}, source, repo_paths)
        if not changed:
            await callback.answer(
                translator.gettext(lang, "global_search_toggle_keep_one"), show_alert=True
            )
            return

        context["filters"] = updated_filters
        await redis_client.set_user_cache(user_id, "global_search", context)

        query = context.get("query", "")
        if query:
            await callback.message.edit_text(translator.gettext(lang, "search_in_progress", query=query))
            await self._run_global_search(
                callback.message,
                user_id,
                query=query,
                filters=updated_filters,
                status_message=callback.message,
            )
        else:
            await self._render_global_search_message(
                callback.message, user_id, is_edit=True, page=0
            )
        await callback.answer()

    async def cq_toggle_global_repo(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id, callback.message.chat.id)
        repo_hash = callback.data.split(":", 1)[1]
        repo_path = kb.code_path_cache.get(repo_hash)
        context = await redis_client.get_user_cache(user_id, "global_search")
        if not repo_path or not context:
            await callback.answer(
                translator.gettext(lang, "search_preset_missing_context"), show_alert=True
            )
            return

        repo_paths = await database.get_user_repos(user_id)
        updated_filters = toggle_global_repo(context.get("filters") or {}, repo_path, repo_paths)
        context["filters"] = updated_filters
        await redis_client.set_user_cache(user_id, "global_search", context)

        query = context.get("query", "")
        if query:
            await callback.message.edit_text(translator.gettext(lang, "search_in_progress", query=query))
            await self._run_global_search(
                callback.message,
                user_id,
                query=query,
                filters=updated_filters,
                status_message=callback.message,
            )
        else:
            await self._render_global_search_message(
                callback.message, user_id, is_edit=True, page=0
            )
        await callback.answer()

    async def cq_global_page(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id, callback.message.chat.id)
        context = await redis_client.get_user_cache(user_id, "global_search")
        if not context:
            await callback.answer(
                translator.gettext(lang, "search_preset_missing_context"), show_alert=True
            )
            return

        page = int(callback.data.split(":", 1)[1])
        keyboard = await self._build_global_search_keyboard(user_id, page=page)
        text = await self._build_global_search_text(user_id, page=page)
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()

    async def cq_show_global_result(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id, callback.message.chat.id)
        context = await redis_client.get_user_cache(user_id, "global_search")
        if not context:
            await callback.answer(
                translator.gettext(lang, "search_preset_missing_context"), show_alert=True
            )
            return

        try:
            index = int(callback.data.split(":", 1)[1])
            result = context["results"][index]
        except (IndexError, ValueError) as exc:
            logger.warning("Invalid global search result index %s: %s", callback.data, exc)
            await callback.answer(
                translator.gettext(lang, "search_invalid_result"), show_alert=True
            )
            return

        await callback.answer()
        if result.get("kind") == SEARCH_KIND_LIBRARY:
            await library_display.show_code_by_path(
                callback.message,
                user_id,
                result["path"],
                translator.gettext(lang, "search_show_result_header"),
            )
            return

        file_name = result["path"].split("/")[-1]
        status_msg = await callback.message.answer(
            translator.gettext(lang, "github_processing_file", file_name=file_name),
            parse_mode="markdown",
        )
        await github_display.display_github_file(
            callback.message,
            user_id,
            result["repo_path"],
            result["path"],
            status_msg_to_delete=status_msg,
        )

    async def command_search_presets(self, message: Message):
        await self._show_search_presets(message, message.from_user.id, is_edit=False)

    async def _show_search_presets(self, message: Message, user_id: int, is_edit: bool = False):
        lang = await translator.get_language(user_id, message.chat.id)
        presets = await database.get_user_search_presets(user_id)
        if not presets:
            text = translator.gettext(lang, "search_presets_empty")
            if is_edit:
                await message.edit_text(text)
            else:
                await message.answer(text)
            return

        keyboard = self._build_search_presets_keyboard(lang, presets)
        text = translator.gettext(lang, "search_presets_header")
        if is_edit:
            await message.edit_text(text, reply_markup=keyboard)
        else:
            await message.answer(text, reply_markup=keyboard)

    def _build_search_presets_keyboard(
        self, lang: str, presets: list[dict]
    ) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for preset in presets:
            preset_id = preset["id"]
            scope_label = self._get_preset_scope_label(lang, preset.get("search_kind"))
            builder.row(
                InlineKeyboardButton(
                    text=f"▶️ [{scope_label}] {preset['name']}",
                    callback_data=f"search_preset_run:{preset_id}",
                ),
                InlineKeyboardButton(
                    text="🗑️",
                    callback_data=f"search_preset_delete:{preset_id}",
                ),
            )
        return builder.as_markup()

    def _get_preset_scope_label(self, lang: str, search_kind: str | None) -> str:
        key_map = {
            SEARCH_KIND_LIBRARY: "search_preset_scope_library",
            SEARCH_KIND_GITHUB: "search_preset_scope_github",
            SEARCH_KIND_SCHEDULE: "search_preset_scope_schedule",
            SEARCH_KIND_GLOBAL: "search_preset_scope_global",
        }
        return translator.gettext(lang, key_map.get(search_kind, "search_preset_scope_global"))

    async def cq_save_search_preset(self, callback: CallbackQuery, state: FSMContext):
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id, callback.message.chat.id)
        search_kind = callback.data.split(":", 1)[1]
        draft = await self._build_search_preset_draft(user_id, search_kind)
        if not draft:
            await callback.answer(
                translator.gettext(lang, "search_preset_missing_context"), show_alert=True
            )
            return

        await state.set_state(SearchCenterStates.awaiting_preset_name)
        await state.update_data(search_preset_draft=draft)
        await callback.message.answer(translator.gettext(lang, "search_preset_name_prompt"))
        await callback.answer()

    async def _build_search_preset_draft(self, user_id: int, search_kind: str) -> dict | None:
        cache_key_map = {
            SEARCH_KIND_LIBRARY: "lib_search",
            SEARCH_KIND_GITHUB: "md_search",
            SEARCH_KIND_SCHEDULE: "schedule_search",
            SEARCH_KIND_GLOBAL: "global_search",
        }
        cache_key = cache_key_map.get(search_kind)
        if not cache_key:
            return None

        cached_data = await redis_client.get_user_cache(user_id, cache_key)
        if not cached_data or not cached_data.get("query"):
            return None

        if search_kind == SEARCH_KIND_LIBRARY:
            filters = {}
        elif search_kind == SEARCH_KIND_GITHUB:
            repo_path = cached_data.get("repo_path")
            if not repo_path:
                return None
            filters = {"repo_paths": [repo_path]}
        elif search_kind == SEARCH_KIND_SCHEDULE:
            filters = {"search_type": cached_data.get("search_type")}
        else:
            filters = cached_data.get("filters") or {}

        return {
            "search_kind": search_kind,
            "query": cached_data["query"],
            "filters": filters,
        }

    async def process_preset_name(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        lang = await translator.get_language(user_id, message.chat.id)
        name = (message.text or "").strip()[:60]
        if not name:
            await message.answer(translator.gettext(lang, "search_preset_empty_name"))
            return

        state_data = await state.get_data()
        draft = state_data.get("search_preset_draft")
        if not draft:
            await state.clear()
            await message.answer(translator.gettext(lang, "search_preset_missing_context"))
            return

        await database.save_user_search_preset(
            user_id=user_id,
            name=name,
            search_kind=draft["search_kind"],
            query=draft["query"],
            filters=draft["filters"],
        )
        await state.clear()
        await message.answer(translator.gettext(lang, "search_preset_saved", name=name))
        await self._show_search_presets(message, user_id, is_edit=False)

    async def cq_run_search_preset(self, callback: CallbackQuery, state: FSMContext):
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id, callback.message.chat.id)
        preset_id = callback.data.split(":", 1)[1]
        preset = await database.get_user_search_preset(user_id, preset_id)
        if not preset:
            await callback.answer(
                translator.gettext(lang, "search_preset_not_found"), show_alert=True
            )
            return

        await state.clear()
        await callback.answer()

        search_kind = preset.get("search_kind")
        query = preset.get("query", "")
        filters = preset.get("filters") or {}

        if search_kind == SEARCH_KIND_LIBRARY:
            await self._run_library_search(callback.message, user_id, query)
            return

        if search_kind == SEARCH_KIND_GITHUB:
            repo_path = next(iter(filters.get("repo_paths") or []), None)
            current_repos = await database.get_user_repos(user_id)
            if not repo_path or repo_path not in current_repos:
                await callback.message.answer(
                    translator.gettext(
                        lang,
                        "search_preset_github_repo_missing",
                        repo_path=repo_path or "-",
                    )
                )
                return
            await self._run_github_search(callback.message, user_id, query, repo_path)
            return

        if search_kind == SEARCH_KIND_SCHEDULE:
            search_type = filters.get("search_type") or "group"
            status_msg = await callback.message.answer(
                translator.gettext(lang, "schedule_search_started")
            )
            await self.schedule_manager._perform_search_and_reply(
                callback.message,
                status_msg,
                query.lower(),
                search_type,
            )
            return

        await self._run_global_search(
            callback.message,
            user_id,
            query,
            filters=filters,
            status_message=None,
        )

    async def _run_library_search(self, message: Message, user_id: int, query: str):
        lang = await translator.get_language(user_id, message.chat.id)
        status_msg = await message.answer(translator.gettext(lang, "search_in_progress", query=query))
        results = await search_library_examples(query, limit=20)

        formatted_results = [{"path": item["path"], "score": item["score"]} for item in results]
        if not formatted_results:
            await status_msg.edit_text(translator.gettext(lang, "search_no_results", query=query))
            return

        await redis_client.set_user_cache(
            user_id, "lib_search", {"query": query, "results": formatted_results}
        )
        keyboard = await self.library_manager._get_search_results_keyboard(user_id, page=0)
        total_pages = (
            len(formatted_results) + SEARCH_RESULTS_PER_PAGE - 1
        ) // SEARCH_RESULTS_PER_PAGE
        await status_msg.edit_text(
            translator.gettext(
                lang,
                "search_results_found",
                count=len(formatted_results),
                query=query,
                page=1,
                total_pages=total_pages,
            ),
            reply_markup=keyboard,
        )

    async def _run_github_search(self, message: Message, user_id: int, query: str, repo_path: str):
        lang = await translator.get_language(user_id, message.chat.id)
        status_msg = await message.answer(
            translator.gettext(lang, "github_search_in_progress", query=query, repo_path=repo_path),
            parse_mode="markdown",
        )
        results = await search_repository_markdown(query, repo_path, limit=10)
        formatted_results = [{"path": item["path"], "score": item["score"]} for item in results]

        if not formatted_results:
            await status_msg.edit_text(
                translator.gettext(lang, "github_search_no_results", query=query)
            )
            return

        await redis_client.set_user_cache(
            user_id,
            "md_search",
            {"query": query, "results": formatted_results, "repo_path": repo_path},
        )
        keyboard = await self.github_manager._get_md_search_results_keyboard(user_id, page=0)
        total_pages = (
            len(formatted_results) + SEARCH_RESULTS_PER_PAGE - 1
        ) // SEARCH_RESULTS_PER_PAGE
        await status_msg.edit_text(
            translator.gettext(
                lang,
                "github_search_results_found",
                count=len(formatted_results),
                repo_path=repo_path,
                query=query,
                page=1,
                total_pages=total_pages,
            ),
            reply_markup=keyboard,
        )

    async def cq_delete_search_preset(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id, callback.message.chat.id)
        preset_id = callback.data.split(":", 1)[1]
        deleted = await database.delete_user_search_preset(user_id, preset_id)
        if not deleted:
            await callback.answer(
                translator.gettext(lang, "search_preset_not_found"), show_alert=True
            )
            return

        await self._show_search_presets(callback.message, user_id, is_edit=True)
        await callback.answer(translator.gettext(lang, "search_preset_deleted"))

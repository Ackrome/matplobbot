from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from aiogram.filters import  Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
import matplobblib
import hashlib
import logging

from .. import keyboards as kb, database
from shared_lib.redis_client import redis_client
from ..services import library_display
from ..config import *
from shared_lib.i18n import translator

class Search(StatesGroup):
    query = State()

class LibraryManager:
    def __init__(self):
        self.router = Router()
        self._register_handlers()

    def _register_handlers(self):
        # Browse
        self.router.message(Command('matp_all'))(self.matp_all_command_inline)
        self.router.callback_query(F.data.startswith("matp_all_nav_hash:"))(self.cq_matp_all_navigate)
        self.router.callback_query(F.data.startswith("matp_all_show:"))(self.cq_matp_all_show_code)
        # Search
        self.router.message(Command('matp_search'))(self.search_command)
        self.router.message(Search.query)(self.process_search_query)
        self.router.callback_query(F.data.startswith("search_page:"))(self.cq_search_pagination)
        self.router.callback_query(F.data.startswith("show_search_idx:"))(self.cq_show_search_result_by_index)
        # Favorites
        self.router.message(Command('favorites'))(self.favorites_command)
        self.router.callback_query(F.data.startswith("fav_hash:"))(self.cq_add_favorite)
        self.router.callback_query(F.data.startswith("fav_del_hash:"))(self.cq_delete_favorite)
        self.router.callback_query(F.data.startswith("show_fav_hash:"))(self.cq_show_favorite)
        # Generic
        self.router.callback_query(F.data == "noop")(self.cq_noop)

    async def _display_matp_all_navigation(self, message: Message, path: str = "", page: int = 0, is_edit: bool = False):
        lang = await translator.get_user_language(message.from_user.id)
        path_parts = path.split('.') if path else []
        level = len(path_parts)
        builder = InlineKeyboardBuilder()
        header_text = ""

        if level == 0:
            header_text = translator.gettext(lang, "matp_all_select_submodule")
            items = sorted(matplobblib.submodules)
            for item in items:
                path_hash = hashlib.sha1(item.encode()).hexdigest()[:16]
                kb.code_path_cache[path_hash] = item
                builder.row(InlineKeyboardButton(text=f"📁 {item}", callback_data=f"matp_all_nav_hash:{path_hash}:0"))
        
        elif level == 1:
            submodule = path_parts[0]
            header_text = translator.gettext(lang, "matp_all_select_topic", submodule=submodule)
            all_topics = sorted(kb.topics_data.get(submodule, {}).get('topics', []))
            start, end = page * SEARCH_RESULTS_PER_PAGE, (page + 1) * SEARCH_RESULTS_PER_PAGE
            for item in all_topics[start:end]:
                full_path = f"{submodule}.{item}"
                path_hash = hashlib.sha1(full_path.encode()).hexdigest()[:16]
                kb.code_path_cache[path_hash] = full_path
                builder.row(InlineKeyboardButton(text=f"📚 {item}", callback_data=f"matp_all_nav_hash:{path_hash}:0"))
            
            builder.row(InlineKeyboardButton(text=translator.gettext(lang, "matp_all_back_to_submodules"), callback_data="matp_all_nav_hash:root:0"))
            self._add_pagination(builder, path, page, len(all_topics), "matp_all_nav_hash")

        elif level == 2:
            submodule, topic = path_parts
            header_text = translator.gettext(lang, "matp_all_select_code", topic=topic)
            all_codes = sorted(kb.topics_data.get(submodule, {}).get('codes', {}).get(topic, []))
            start, end = page * SEARCH_RESULTS_PER_PAGE, (page + 1) * SEARCH_RESULTS_PER_PAGE
            for item in all_codes[start:end]:
                full_code_path = f"{path}.{item}"
                path_hash = hashlib.sha1(full_code_path.encode()).hexdigest()[:16]
                kb.code_path_cache[path_hash] = full_code_path
                builder.row(InlineKeyboardButton(text=f"📄 {item}", callback_data=f"matp_all_show:{path_hash}"))

            back_path = submodule
            path_hash = hashlib.sha1(back_path.encode()).hexdigest()[:16]
            kb.code_path_cache[path_hash] = back_path
            builder.row(InlineKeyboardButton(text=translator.gettext(lang, "matp_all_back_to_topics"), callback_data=f"matp_all_nav_hash:{path_hash}:0"))
            self._add_pagination(builder, path, page, len(all_codes), "matp_all_nav_hash")

        else:
            header_text = translator.gettext(lang, "matp_all_navigation_error")

        try:
            if is_edit:
                await message.edit_text(header_text, reply_markup=builder.as_markup(), parse_mode='markdown')
            else:
                await message.answer(header_text, reply_markup=builder.as_markup(), parse_mode='markdown')
        except TelegramBadRequest as e:
            if "message is not modified" not in e.message: raise

    def _add_pagination(self, builder: InlineKeyboardBuilder, path: str, page: int, total_items: int, callback_prefix: str):
        total_pages = (total_items + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE
        if total_pages > 1:
            pagination_buttons = []
            path_hash = hashlib.sha1(path.encode()).hexdigest()[:16]
            kb.code_path_cache[path_hash] = path
            if page > 0:
                pagination_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"{callback_prefix}:{path_hash}:{page - 1}"))
            pagination_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
            if (page + 1) * SEARCH_RESULTS_PER_PAGE < total_items:
                pagination_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"{callback_prefix}:{path_hash}:{page + 1}"))
            builder.row(*pagination_buttons)

    async def matp_all_command_inline(self, message: Message):
        await self._display_matp_all_navigation(message, path="", page=0, is_edit=False)

    async def cq_matp_all_navigate(self, callback: CallbackQuery):
        parts = callback.data.split(":")
        path_hash, page = parts[1], int(parts[2])
        path = "" if path_hash == 'root' else kb.code_path_cache.get(path_hash)
        lang = await translator.get_user_language(callback.from_user.id)
        if path is None:
            await callback.answer(translator.gettext(lang, "matp_all_show_error"), show_alert=True)
            return
        await callback.answer()
        await self._display_matp_all_navigation(callback.message, path=path, page=page, is_edit=True)

    async def cq_matp_all_show_code(self, callback: CallbackQuery):
        path_hash = callback.data.split(":", 1)[1]
        lang = await translator.get_user_language(callback.from_user.id)
        code_path = kb.code_path_cache.get(path_hash)
        if not code_path:
            await callback.answer(translator.gettext(lang, "matp_all_show_error"), show_alert=True)
            return
        await callback.answer()
        await library_display.show_code_by_path(callback.message, callback.from_user.id, code_path, translator.gettext(lang, "matp_all_selected_example"))

    async def _get_search_results_keyboard(self, user_id: int, page: int = 0) -> InlineKeyboardMarkup | None:
        search_data = await redis_client.get_user_cache(user_id, 'lib_search')
        if not search_data or not search_data.get('results'):
            return None

        results = search_data['results']
        builder = InlineKeyboardBuilder()
        start, end = page * SEARCH_RESULTS_PER_PAGE, (page + 1) * SEARCH_RESULTS_PER_PAGE
        lang = await translator.get_user_language(user_id)

        for i, result in enumerate(results[start:end]):
            global_index = start + i
            builder.row(InlineKeyboardButton(text=f"▶️ {result['path']}", callback_data=f"show_search_idx:{global_index}"))

        total_pages = (len(results) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE
        if total_pages > 1:
            pagination_buttons = []
            if page > 0: pagination_buttons.append(InlineKeyboardButton(text=translator.gettext(lang, "pagination_back"), callback_data=f"search_page:{page - 1}"))
            pagination_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
            if end < len(results): pagination_buttons.append(InlineKeyboardButton(text=translator.gettext(lang, "pagination_forward"), callback_data=f"search_page:{page + 1}"))
            builder.row(*pagination_buttons)

        return builder.as_markup()

    async def _perform_full_text_search(self, query: str) -> list[dict]:
        keywords = query.lower().split()
        if not keywords: return []
        found_items, found_paths = [], set()

        for submodule_name in matplobblib.submodules:
            try:
                module = matplobblib._importlib.import_module(f'matplobblib.{submodule_name}')
                code_dictionary = module.themes_list_dicts_full
                for topic_name, codes in code_dictionary.items():
                    for code_name, code_content in codes.items():
                        code_path = f"{submodule_name}.{topic_name}.{code_name}"
                        if code_path in found_paths: continue
                        search_corpus = f"{submodule_name} {topic_name} {code_name} {code_content}".lower()
                        if all(keyword in search_corpus for keyword in keywords):
                            found_items.append({'path': code_path, 'name': code_name})
                            found_paths.add(code_path)
            except Exception as e:
                logging.error(f"Ошибка при поиске в подмодуле {submodule_name}: {e}")
        return found_items

    async def search_command(self, message: Message, state: FSMContext):
        lang = await translator.get_user_language(message.from_user.id)
        await state.set_state(Search.query)
        await message.answer(translator.gettext(lang, "search_prompt_library"), reply_markup=ReplyKeyboardRemove())

    async def process_search_query(self, message: Message, state: FSMContext):
        await state.clear()
        user_id, lang, query = message.from_user.id, await translator.get_user_language(message.from_user.id), message.text
        status_msg = await message.answer(translator.gettext(lang, "search_in_progress", query=query))
        results = await self._perform_full_text_search(query)

        if not results:
            await status_msg.edit_text(translator.gettext(lang, "search_no_results", query=query))
            await message.answer(translator.gettext(lang, "choose_next_command"), reply_markup=await kb.get_main_reply_keyboard(user_id))
            return

        await redis_client.set_user_cache(user_id, 'lib_search', {'query': query, 'results': results})
        keyboard = await self._get_search_results_keyboard(user_id, page=0)
        total_pages = (len(results) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE
        await status_msg.edit_text(translator.gettext(lang, "search_results_found", count=len(results), query=query, page=1, total_pages=total_pages), reply_markup=keyboard)

    async def cq_search_pagination(self, callback: CallbackQuery):
        user_id, lang = callback.from_user.id, await translator.get_user_language(callback.from_user.id)
        search_data = await redis_client.get_user_cache(user_id, 'lib_search')
        if not search_data:
            await callback.answer(translator.gettext(lang, "search_results_outdated"), show_alert=True)
            await callback.message.delete()
            return

        page = int(callback.data.split(":", 1)[1])
        keyboard = await self._get_search_results_keyboard(user_id, page=page)
        results, query = search_data['results'], search_data['query']
        total_pages = (len(results) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE
        await callback.message.edit_text(translator.gettext(lang, "search_results_found", count=len(results), query=query, page=page + 1, total_pages=total_pages), reply_markup=keyboard)
        await callback.answer()

    async def _show_favorites_menu(self, message: Message, user_id: int, is_edit: bool = False):
        lang = await translator.get_user_language(user_id)
        favs = await database.get_favorites(user_id)
        if not favs:
            text = translator.gettext(lang, "favorites_empty")
            reply_markup = await kb.get_main_reply_keyboard(user_id) if not is_edit else None
            if is_edit: await message.edit_text(text, reply_markup=reply_markup)
            else: await message.answer(text, reply_markup=reply_markup)
            return

        builder = InlineKeyboardBuilder()
        for code_path in favs:
            path_hash = hashlib.sha1(code_path.encode()).hexdigest()[:16]
            kb.code_path_cache[path_hash] = code_path
            builder.row(
                InlineKeyboardButton(text=f"📄 {code_path}", callback_data=f"show_fav_hash:{path_hash}"),
                InlineKeyboardButton(text=translator.gettext(lang, "favorites_remove_btn"), callback_data=f"fav_del_hash:{path_hash}")
            )
        
        text = translator.gettext(lang, "favorites_header")
        if is_edit: await message.edit_text(text, reply_markup=builder.as_markup())
        else: await message.answer(text, reply_markup=builder.as_markup())

    async def favorites_command(self, message: Message):
        await self._show_favorites_menu(message, message.from_user.id)

    async def cq_add_favorite(self, callback: CallbackQuery):
        path_hash = callback.data.split(":", 1)[1]
        lang = await translator.get_user_language(callback.from_user.id)
        code_path = kb.code_path_cache.get(path_hash)
        if not code_path:
            await callback.answer(translator.gettext(lang, "matp_all_show_error"), show_alert=True)
            return
        success = await database.add_favorite(callback.from_user.id, code_path)
        await callback.answer(translator.gettext(lang, "favorites_added_success" if success else "favorites_already_exists"), show_alert=False)

    async def cq_delete_favorite(self, callback: CallbackQuery):
        user_id, lang = callback.from_user.id, await translator.get_user_language(callback.from_user.id)
        path_hash = callback.data.split(":", 1)[1]
        code_path = kb.code_path_cache.get(path_hash)
        if not code_path:
            await callback.answer(translator.gettext(lang, "favorites_info_outdated"), show_alert=True)
            return

        await database.remove_favorite(user_id, code_path)
        await callback.answer(translator.gettext(lang, "favorites_removed"), show_alert=False)
        await self._show_favorites_menu(callback.message, user_id, is_edit=True)

    async def cq_noop(self, callback: CallbackQuery):
        await callback.answer()

    async def cq_show_search_result_by_index(self, callback: CallbackQuery):
        user_id, lang = callback.from_user.id, await translator.get_user_language(callback.from_user.id)
        search_data = await redis_client.get_user_cache(user_id, 'lib_search')
        if not search_data:
            await callback.answer(translator.gettext(lang, "search_results_outdated"), show_alert=True)
            return

        try:
            index = int(callback.data.split(":", 1)[1])
            code_path = search_data['results'][index]['path']
            await callback.answer()
            await library_display.show_code_by_path(callback.message, user_id, code_path, translator.gettext(lang, "search_show_result_header"))
        except (ValueError, IndexError) as e:
            logging.warning(f"Invalid search index from user {user_id}. Data: {callback.data}. Error: {e}")
            await callback.answer(translator.gettext(lang, "search_invalid_result"), show_alert=True)

    async def cq_show_favorite(self, callback: CallbackQuery):
        path_hash = callback.data.split(":", 1)[1]
        lang = await translator.get_user_language(callback.from_user.id)
        code_path = kb.code_path_cache.get(path_hash)
        if not code_path:
            await callback.answer(translator.gettext(lang, "favorites_info_outdated"), show_alert=True)
            return
        await callback.answer()
        await library_display.show_code_by_path(callback.message, callback.from_user.id, code_path, translator.gettext(lang, "search_show_favorite_header"))

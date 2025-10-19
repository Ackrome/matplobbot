from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from aiogram.filters import  Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder

import matplotlib
matplotlib.use('Agg') # Use a non-interactive backend for server environments
import matplobblib
import hashlib
import logging

from .. import keyboards as kb, database
from ..redis_client import redis_client
from ..services import library_display # <-- обновим импорт на Шаге 2
from ..config import *
from ..i18n import translator

router = Router()


##################################################################################################
# ASK
##################################################################################################
class Search(StatesGroup):
    query = State()

async def display_matp_all_navigation(message: Message, path: str = "", page: int = 0, is_edit: bool = False):
    """Helper to display navigation for /matp_all command."""
    lang = await translator.get_user_language(message.from_user.id)
    path_parts = path.split('.') if path else []
    level = len(path_parts)
    
    builder = InlineKeyboardBuilder()
    header_text = ""

    # Level 0: Submodules
    if level == 0:
        header_text = translator.gettext(lang, "matp_all_select_submodule")
        items = sorted(matplobblib.submodules)
        # No pagination for submodules, assuming list is short
        for item in items:
            path_hash = hashlib.sha1(item.encode()).hexdigest()[:16]
            kb.code_path_cache[path_hash] = item
            builder.row(InlineKeyboardButton(text=f"📁 {item}", callback_data=f"matp_all_nav_hash:{path_hash}:0"))
    
    # Level 1: Topics
    elif level == 1:
        submodule = path_parts[0]
        header_text = translator.gettext(lang, "matp_all_select_topic", submodule=submodule)
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
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "matp_all_back_to_submodules"), callback_data="matp_all_nav_hash:root:0"))
        
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
        header_text = translator.gettext(lang, "matp_all_select_code", topic=topic)
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
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "matp_all_back_to_topics"), callback_data=f"matp_all_nav_hash:{path_hash}:0"))

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
        header_text = translator.gettext(lang, "matp_all_navigation_error")

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

    lang = await translator.get_user_language(callback.from_user.id)
    if path is None:
        await callback.answer(translator.gettext(lang, "matp_all_show_error"), show_alert=True)
        return

    await callback.answer()
    await display_matp_all_navigation(callback.message, path=path, page=page, is_edit=True)

@router.callback_query(F.data.startswith("matp_all_show:"))
async def cq_matp_all_show_code(callback: CallbackQuery):
    """Shows the selected code from the /matp_all navigation."""
    path_hash = callback.data.split(":", 1)[1]
    lang = await translator.get_user_language(callback.from_user.id)
    code_path = kb.code_path_cache.get(path_hash)
    if not code_path:
        await callback.answer(translator.gettext(lang, "matp_all_show_error"), show_alert=True)
        return
    
    await callback.answer()
    await library_display.show_code_by_path(callback.message, callback.from_user.id, code_path, translator.gettext(lang, "matp_all_selected_example"))


##################################################################################################
# SEARCH & FAVORITES
##################################################################################################

async def get_search_results_keyboard(user_id: int, page: int = 0) -> InlineKeyboardMarkup | None:
    """Создает инлайн-клавиатуру для страницы результатов поиска с пагинацией."""
    search_data = await redis_client.get_user_cache(user_id, 'lib_search')
    if not search_data or not search_data.get('results'):
        return None

    results = search_data['results']
    builder = InlineKeyboardBuilder()
    
    start = page * SEARCH_RESULTS_PER_PAGE
    end = start + SEARCH_RESULTS_PER_PAGE
    page_items = results[start:end]
    lang = await translator.get_user_language(user_id)

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
            pagination_buttons.append(InlineKeyboardButton(text=translator.gettext(lang, "pagination_back"), callback_data=f"search_page:{page - 1}"))
        
        pagination_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))

        if end < len(results):
            pagination_buttons.append(InlineKeyboardButton(text=translator.gettext(lang, "pagination_forward"), callback_data=f"search_page:{page + 1}"))
        
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
    lang = await translator.get_user_language(message.from_user.id)
    await state.set_state(Search.query)
    await message.answer(translator.gettext(lang, "search_prompt_library"), reply_markup=ReplyKeyboardRemove())

@router.message(Search.query)
async def process_search_query(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    lang = await translator.get_user_language(user_id)
    query = message.text
    status_msg = await message.answer(translator.gettext(lang, "search_in_progress", query=query))
    results = await perform_full_text_search(query)

    if not results:
        await status_msg.edit_text(
            translator.gettext(lang, "search_no_results", query=query)
        )
        # Отправляем основную клавиатуру отдельным сообщением, так как edit_text не может ее использовать
        await message.answer(translator.gettext(lang, "choose_next_command"), reply_markup=await kb.get_main_reply_keyboard(user_id))
        return

    # Store query and results in cache for this user
    await redis_client.set_user_cache(user_id, 'lib_search', {'query': query, 'results': results})

    keyboard = await get_search_results_keyboard(user_id, page=0)
    total_pages = (len(results) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE

    await status_msg.edit_text(
        translator.gettext(lang, "search_results_found", count=len(results), query=query, page=1, total_pages=total_pages),
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("search_page:"))
async def cq_search_pagination(callback: CallbackQuery):
    """Обрабатывает нажатия на кнопки пагинации в результатах поиска."""
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    search_data = await redis_client.get_user_cache(user_id, 'lib_search')
    if not search_data:
        await callback.answer(translator.gettext(lang, "search_results_outdated"), show_alert=True)
        await callback.message.delete()
        return

    page = int(callback.data.split(":", 1)[1])
    keyboard = await get_search_results_keyboard(user_id, page=page)
    
    results = search_data['results']
    query = search_data['query']
    total_pages = (len(results) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE

    await callback.message.edit_text(
        translator.gettext(lang, "search_results_found", count=len(results), query=query, page=page + 1, total_pages=total_pages),
        reply_markup=keyboard
    )
    await callback.answer()

@router.message(Command('favorites'))
async def favorites_command(message: Message):
    user_id = message.from_user.id
    lang = await translator.get_user_language(user_id)
    favs = await database.get_favorites(user_id)
    if not favs:
        await message.answer(translator.gettext(lang, "favorites_empty"), reply_markup=await kb.get_main_reply_keyboard(user_id))
        return

    builder = InlineKeyboardBuilder()
    for code_path in favs:
        path_hash = hashlib.sha1(code_path.encode()).hexdigest()[:16]
        kb.code_path_cache[path_hash] = code_path
        builder.row(
            InlineKeyboardButton(text=f"📄 {code_path}", callback_data=f"show_fav_hash:{path_hash}"),
            InlineKeyboardButton(text=translator.gettext(lang, "favorites_remove_btn"), callback_data=f"fav_del_hash:{path_hash}")
        )
    
    await message.answer(translator.gettext(lang, "favorites_header"), reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("fav_hash:"))
async def cq_add_favorite(callback: CallbackQuery):
    path_hash = callback.data.split(":", 1)[1]
    lang = await translator.get_user_language(callback.from_user.id)
    code_path = kb.code_path_cache.get(path_hash)
    if not code_path:
        await callback.answer(translator.gettext(lang, "matp_all_show_error"), show_alert=True)
        return

    success = await database.add_favorite(callback.from_user.id, code_path)
    if success:
        await callback.answer(translator.gettext(lang, "favorites_added_success"), show_alert=False)
    else:
        await callback.answer(translator.gettext(lang, "favorites_already_exists"), show_alert=False)

@router.callback_query(F.data.startswith("fav_del_hash:"))
async def cq_delete_favorite(callback: CallbackQuery):
    """Обрабатывает удаление примера из избранного."""
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    path_hash = callback.data.split(":", 1)[1]
    code_path = kb.code_path_cache.get(path_hash)

    if not code_path:
        await callback.answer(translator.gettext(lang, "favorites_info_outdated"), show_alert=True)
        return

    # Удаляем из БД
    await database.remove_favorite(user_id, code_path)
    await callback.answer(translator.gettext(lang, "favorites_removed"), show_alert=False)

    # Обновляем сообщение со списком избранного
    favs = await database.get_favorites(user_id)
    if not favs:
        await callback.message.edit_text(translator.gettext(lang, "favorites_list_empty"))
        return

    # Пересобираем клавиатуру
    builder = InlineKeyboardBuilder()
    for new_code_path in favs:
        new_path_hash = hashlib.sha1(new_code_path.encode()).hexdigest()[:16]
        kb.code_path_cache[new_path_hash] = new_code_path
        builder.row(
            InlineKeyboardButton(text=f"📄 {new_code_path}", callback_data=f"show_fav_hash:{new_path_hash}"),
            InlineKeyboardButton(text=translator.gettext(lang, "favorites_remove_btn"), callback_data=f"fav_del_hash:{new_path_hash}")
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
    lang = await translator.get_user_language(user_id)
    search_data = await redis_client.get_user_cache(user_id, 'lib_search')
    if not search_data:
        await callback.answer(translator.gettext(lang, "search_results_outdated"), show_alert=True)
        return

    try:
        index = int(callback.data.split(":", 1)[1])
        results = search_data['results']
        
        if not (0 <= index < len(results)):
            raise IndexError("Search result index out of bounds.")

        code_path = results[index]['path']
        
        await callback.answer() # Acknowledge the callback
        await library_display.show_code_by_path(callback.message, callback.from_user.id, code_path, translator.gettext(lang, "search_show_result_header"))

    except (ValueError, IndexError) as e:
        logging.warning(f"Invalid search index from user {user_id}. Data: {callback.data}. Error: {e}")
        await callback.answer(translator.gettext(lang, "search_invalid_result"), show_alert=True)
    except Exception as e:
        logging.error(f"Error showing search result by index for user {user_id}: {e}", exc_info=True)
        await callback.answer(translator.gettext(lang, "latex_unexpected_error", error=e), show_alert=True)

@router.callback_query(F.data.startswith("show_fav_hash:"))
async def cq_show_favorite(callback: CallbackQuery):
    """Handles clicks on favorite item buttons."""
    path_hash = callback.data.split(":", 1)[1]
    lang = await translator.get_user_language(callback.from_user.id)
    code_path = kb.code_path_cache.get(path_hash)
    if not code_path:
        await callback.answer(translator.gettext(lang, "favorites_info_outdated"), show_alert=True)
        return

    await callback.answer()
    await library_display.show_code_by_path(callback.message, callback.from_user.id, code_path, translator.gettext(lang, "search_show_favorite_header"))

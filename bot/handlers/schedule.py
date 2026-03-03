# bot/handlers/schedule.py

from aiogram import F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from datetime import datetime, timedelta, time, date
import logging, json
import re
import hashlib

from shared_lib.services.university_api import RuzAPIClient # Import the class for type hinting
from bot.keyboards import get_schedule_type_keyboard, build_search_results_keyboard, code_path_cache, get_myschedule_calendar_keyboard, get_myschedule_filters_keyboard, build_calendar_keyboard, InlineKeyboardButton, get_modules_keyboard
from shared_lib.i18n import translator
from bot import database
from shared_lib.redis_client import redis_client
import asyncio
from shared_lib.database import (
    get_cached_schedule,
    upsert_cached_schedule,
    merge_cached_schedule,
    update_subscription_modules,
    get_subscription_modules,
    get_subscription_by_id,
    get_user_subscriptions
)
from shared_lib.services.schedule_service import (
    format_schedule, 
    generate_ical_from_schedule,
    get_semester_bounds,
    get_unique_modules_hybrid,
    generate_ical_from_aggregated_schedule,
    get_module_name,
    get_aggregated_schedule
)

import calendar

router = Router()
module_name_cache = {} 

class ScheduleStates(StatesGroup):
    awaiting_search_query = State()
    awaiting_subscription_time = State()
class ScheduleManager:
    def __init__(self, ruz_api_client: RuzAPIClient):
        self.router = Router()
        self.api_client = ruz_api_client
        self._register_handlers()

    def _register_handlers(self):
        self.router.message(Command("schedule"))(self.cmd_schedule)
        self.router.callback_query(F.data.startswith("sch_type_"))(self.handle_schedule_type)
        self.router.message(ScheduleStates.awaiting_search_query)(self.handle_search_query)
        self.router.callback_query(F.data.startswith("sch_open_calendar:"))(self.handle_open_calendar)
        self.router.callback_query(F.data.startswith("sch_result_"))(self.handle_result_selection)
        self.router.callback_query(F.data.startswith("cal_nav:"))(self.handle_calendar_navigation)
        self.router.callback_query(F.data == "sch_back_to_results")(self.handle_back_to_results)
        self.router.callback_query(F.data.startswith("cal_back:"))(self.handle_back_to_calendar)
        self.router.callback_query(F.data.startswith("sch_date_"))(self.handle_date_selection)
        self.router.callback_query(F.data.startswith("sch_week_"))(self.handle_week_selection)
        self.router.callback_query(F.data.startswith("sch_export_ical:"))(self.handle_ical_export)
        self.router.callback_query(F.data.startswith("sch_subscribe_hash:"))(self.handle_subscribe_button)
        self.router.message(ScheduleStates.awaiting_subscription_time)(self.handle_subscription_time)
        self.router.message(Command("myschedule"))(self.cmd_my_schedule)
        self.router.callback_query(F.data.startswith("sch_history:"))(self.handle_history_selection)
        self.router.callback_query(F.data == "sch_clear_history")(self.handle_clear_history)
        self.router.callback_query(F.data.startswith("mod_toggle:"))(self.handle_module_toggle)
        self.router.callback_query(F.data.startswith("mod_save:"))(self.handle_module_save)
        self.router.callback_query(F.data == "mysch_open_cal")(self.handle_myschedule_open)
        self.router.callback_query(F.data.startswith("mysch_nav:"))(self.handle_myschedule_nav)
        self.router.callback_query(F.data.startswith("mysch_day:"))(self.handle_myschedule_day)
        self.router.callback_query(F.data == "mysch_filters:main")(self.handle_myschedule_filters_menu)
        self.router.callback_query(F.data.startswith("mysch_tog_"))(self.handle_myschedule_toggle_filter)
        self.router.callback_query(F.data == "mysch_back_cal")(self.handle_myschedule_back_to_cal)
        
        self.router.callback_query(F.data.startswith("mysch_week:"))(self.handle_myschedule_week)
        self.router.callback_query(F.data.startswith("mysch_ical:"))(self.handle_myschedule_export_ical)
        
        self.router.callback_query(F.data == "mysch_cal_link")(self.handle_cal_link)
        self.router.callback_query(F.data == "mysch_cal_revoke")(self.handle_cal_revoke)


    async def cmd_schedule(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        lang = await translator.get_language(user_id, message.chat.id)

        # --- NEW: Fetch and display search history ---
        history_key = f"schedule_history:{user_id}"
        history_items_raw = await redis_client.client.lrange(history_key, 0, -1)
        history_items = [json.loads(item) for item in history_items_raw]

        keyboard = await get_schedule_type_keyboard(lang, history_items)

        await message.answer(
            translator.gettext(lang, "schedule_welcome"),
            reply_markup=keyboard
        )

    async def handle_schedule_type(self, callback: CallbackQuery, state: FSMContext):
        search_type = callback.data.split("_")[-1]
        await state.set_state(ScheduleStates.awaiting_search_query)
        await state.update_data(search_type=search_type)
        
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id, callback.message.chat.id)
        
        prompt_key = f"schedule_prompt_for_query_{search_type}"
        await callback.message.edit_text(translator.gettext(lang, prompt_key))
        await callback.answer()

    async def _perform_search_and_reply(self, message: Message, status_msg: Message, query: str, search_type: str):
        """Helper function to run the search in the background and send results."""
        user_id = message.from_user.id
        lang = await translator.get_language(user_id, message.chat.id)
        
        try:
            results = await self.api_client.search(term=query, search_type=search_type)

            if not results:
                await message.answer(translator.gettext(lang, "schedule_no_results", query=query))
                return

            await redis_client.set_user_cache(user_id, 'schedule_search', {'query': query, 'search_type': search_type, 'results': results})
            keyboard = build_search_results_keyboard(results, search_type)
            await message.answer(translator.gettext(lang, "schedule_results_found", count=len(results)), reply_markup=keyboard)
        except asyncio.TimeoutError:
            await message.answer(translator.gettext(lang, "schedule_api_timeout_error"))
        except Exception as e:
            logging.error(f"Failed to query RUZ API in background task. Error: {e}", exc_info=True)
            await message.answer(translator.gettext(lang, "schedule_api_error"))
        finally:
            # Clean up the "search started" message
            await status_msg.delete()

    async def handle_search_query(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        lang = await translator.get_language(user_id, message.chat.id)
        # Add a guard clause to handle non-text messages (like group upgrades)
        if not message.text:
            await message.reply(translator.gettext(lang, "schedule_invalid_time_format")) # A generic error is fine
            return

        data = await state.get_data()
        search_type = data['search_type']
        query = message.text.lower()
        await state.clear()

        # Immediately respond and start the search in the background
        status_msg = await message.answer(translator.gettext(lang, "schedule_search_started"))
        asyncio.create_task(self._perform_search_and_reply(message, status_msg, query, search_type))

    async def handle_result_selection(self, callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        _, entity_type, entity_id = callback.data.split(":")
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id, callback.message.chat.id)
        await callback.message.edit_text(translator.gettext(lang, "schedule_loading"))

        try:
            today = datetime.now()
            api_date_str = today.strftime("%Y-%m-%d")

            # --- ЛОГИКА КЭШИРОВАНИЯ ---
            schedule_data = []
            cached_full_schedule = await get_cached_schedule(entity_type, entity_id)
            
            lessons_today_in_cache = []
            if cached_full_schedule:
                lessons_today_in_cache = [l for l in cached_full_schedule if l['date'] == api_date_str]
            
            if lessons_today_in_cache:
                logging.info(f"Using cached schedule for {entity_type}:{entity_id} (Date: {api_date_str})")
                schedule_data = lessons_today_in_cache
            else:
                logging.info(f"Cache miss for {entity_type}:{entity_id}, fetching from API")
                schedule_data = await self.api_client.get_schedule(entity_type, entity_id, start=api_date_str, finish=api_date_str)
                await merge_cached_schedule(entity_type, entity_id, schedule_data, target_dates=[api_date_str])

            # --- ИСПОЛЬЗУЕМ НОВЫЙ МЕТОД ВОССТАНОВЛЕНИЯ ИМЕНИ ---
            entity_name = await self._resolve_entity_name(user_id, entity_type, entity_id, schedule_data)
            
            # Если имя нашлось, сохраняем в историю (даже если не из поиска пришло)
            if entity_name != "Unknown":
                history_key = f"schedule_history:{user_id}"
                history_item = json.dumps({
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "entity_name": entity_name
                })
                await redis_client.client.lrem(history_key, 0, history_item)
                await redis_client.client.lpush(history_key, history_item)
                await redis_client.client.ltrim(history_key, 0, 4)

            formatted_text = await format_schedule(schedule_data, lang, entity_name, entity_type, user_id, start_date=today.date())

            await callback.message.edit_text(formatted_text, parse_mode="HTML")
            await self._send_actions_menu(callback.message, lang, entity_type, entity_id, entity_name, view_type='daily_initial')
        except Exception as e:
            logging.error(f"Failed to get today's schedule for {entity_type}:{entity_id}. Error: {e}", exc_info=True)
            await callback.message.edit_text(translator.gettext(lang, "schedule_api_error"))
            
    async def handle_history_selection(self, callback: CallbackQuery, state: FSMContext):
        """Handles clicks on the new history buttons."""
        # The data format is sch_history:{entity_type}:{entity_id}.
        # We reuse the existing result selection handler. Since the callback object is immutable,
        # we create a copy with the modified 'data' attribute to match the expected format.
        new_data = callback.data.replace("sch_history:", "sch_result_:")
        modified_callback = callback.model_copy(update={'data': new_data})
        await self.handle_result_selection(modified_callback, state)

    async def handle_clear_history(self, callback: CallbackQuery, state: FSMContext):
        """Handles the 'Clear History' button click."""
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id, callback.message.chat.id)
        history_key = f"schedule_history:{user_id}"
        await redis_client.client.delete(history_key)

        # Refresh the menu to show the history is gone
        keyboard = await get_schedule_type_keyboard(lang, history_items=[])
        await callback.message.edit_reply_markup(reply_markup=keyboard)

        # Notify the user
        await callback.answer(translator.gettext(lang, "schedule_history_cleared"))

    async def handle_open_calendar(self, callback: CallbackQuery):
        await callback.answer()
        _, entity_type, entity_id = callback.data.split(":")
        lang = await translator.get_language(callback.from_user.id, callback.message.chat.id)
        now = datetime.now()

        # --- FIX for BUTTON_DATA_INVALID ---
        # If entity_id is long (like a UUID), cache it and use a hash instead.
        if len(entity_id) > 32:
            id_hash = hashlib.sha1(entity_id.encode()).hexdigest()[:16]
            code_path_cache[id_hash] = entity_id
            entity_id_for_callback = id_hash
        else:
            entity_id_for_callback = entity_id
        # --- END FIX ---

        calendar_keyboard = build_calendar_keyboard(now.year, now.month, entity_type, entity_id_for_callback, lang)
        await callback.message.edit_text(translator.gettext(lang, "schedule_select_date"), reply_markup=calendar_keyboard)

    async def handle_calendar_navigation(self, callback: CallbackQuery):
        await callback.answer()
        try:
            _, action, year_str, month_str, entity_type, entity_id = callback.data.split(":")
            year, month = int(year_str), int(month_str)

            # --- FIX for BUTTON_DATA_INVALID ---
            # If the ID is a hash, retrieve the full ID from the cache.
            # This doesn't affect the calendar build, as it will just pass the hash along.
            if len(entity_id) == 16 and not entity_id.isdigit(): # Heuristic for our hash
                pass # The entity_id is already the hash we need for callbacks.

            if action == "prev_month": month -= 1; year = year - 1 if month == 0 else year; month = 12 if month == 0 else month
            elif action == "next_month": month += 1; year = year + 1 if month == 13 else year; month = 1 if month == 13 else month
            elif action == "prev_year": year -= 1
            elif action == "next_year": year += 1
            elif action == "today":
                now = datetime.now()
                # Check if we are already on the current month
                if now.year == int(year_str) and now.month == int(month_str):
                    await callback.answer(translator.gettext(await translator.get_language(callback.from_user.id, callback.message.chat.id), "calendar_already_on_today"), show_alert=False)
                    return
                year, month = now.year, now.month

            lang = await translator.get_language(callback.from_user.id, callback.message.chat.id)
            try:
                await callback.message.edit_reply_markup(reply_markup=build_calendar_keyboard(year, month, entity_type, entity_id, lang))
            except TelegramBadRequest as e:
                if "message is not modified" in e.message:
                    # This case should be rarer now, but we keep it as a fallback.
                    await callback.answer(translator.gettext(lang, "calendar_already_on_today"), show_alert=False)
                else:
                    raise # Re-raise other bad requests
        except (ValueError, IndexError) as e:
            logging.error(f"Error handling calendar navigation: {e}. Data: {callback.data}")

    async def handle_back_to_results(self, callback: CallbackQuery):
        await callback.answer()
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id, callback.message.chat.id)
        cached_data = await redis_client.get_user_cache(user_id, 'schedule_search')
        if not cached_data:
            await callback.message.edit_text(translator.gettext(lang, "search_results_outdated"))
            return
        keyboard = build_search_results_keyboard(cached_data['results'], cached_data['search_type'])
        await callback.message.edit_text(translator.gettext(lang, "schedule_results_found", count=len(cached_data['results'])), reply_markup=keyboard)

    async def handle_back_to_calendar(self, callback: CallbackQuery):
        await callback.answer()
        try:
            _, year_str, month_str, entity_type, entity_id, selected_date_str = callback.data.split(":")
            year, month = int(year_str), int(month_str)

            # --- FIX for BUTTON_DATA_INVALID ---
            # If the ID is a hash, retrieve the full ID from the cache.
            if len(entity_id) == 16 and not entity_id.isdigit():
                pass # Keep the hash for building the next calendar view

            selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()
            lang = await translator.get_language(callback.from_user.id, callback.message.chat.id)
            calendar_keyboard = build_calendar_keyboard(year, month, entity_type, entity_id, lang, selected_date=selected_date)
            await callback.message.edit_text(translator.gettext(lang, "schedule_select_date"), reply_markup=calendar_keyboard)
        except (ValueError, IndexError) as e:
            logging.error(f"Error handling back to calendar navigation: {e}. Data: {callback.data}")

    async def _send_actions_menu(self, message: Message, lang: str, entity_type: str, entity_id: str, entity_name: str, view_type: str, date_info: dict = None):
        """Sends a follow-up message with a keyboard of contextual actions."""
        keyboard = self._build_schedule_actions_keyboard(lang, entity_type, entity_id, entity_name, view_type, date_info)
        await message.answer(
            translator.gettext(lang, "schedule_actions_prompt"),
            reply_markup=keyboard.as_markup()
        )

    def _build_schedule_actions_keyboard(self, lang: str, entity_type: str, entity_id: str, entity_name: str, view_type: str, date_info: dict | None = None) -> InlineKeyboardBuilder:
        """Builds a contextual keyboard for schedule-related actions."""
        builder = InlineKeyboardBuilder()
        
        # Subscribe button (always relevant)
        subscribe_button_data = build_search_results_keyboard(
            [{'label': translator.gettext(lang, "schedule_subscribe_button"), 'id': f"{entity_type}:{entity_id}:{entity_name}"}], 'subscribe'
        )
        builder.row(subscribe_button_data.inline_keyboard[0][0])

        # --- FIX: Hash entity_id if it's too long to avoid BUTTON_DATA_INVALID ---
        safe_entity_id = entity_id
        if len(entity_id) > 20: # UUIDs are 36 chars, hashing reduces to 16
            id_hash = hashlib.sha1(entity_id.encode()).hexdigest()[:16]
            code_path_cache[id_hash] = entity_id
            safe_entity_id = id_hash
        # --- END FIX ---

        # Context-specific buttons
        if view_type == 'daily_initial': # After initial search result
            open_calendar_callback = f"sch_open_calendar:{entity_type}:{safe_entity_id}"
            today_str = datetime.now().strftime("%Y-%m-%d")
            ical_callback = f"sch_export_ical:{entity_type}:{safe_entity_id}:{today_str}"
            
            builder.row(InlineKeyboardButton(text=translator.gettext(lang, "schedule_export_ical"), callback_data=ical_callback))
            builder.row(InlineKeyboardButton(text=translator.gettext(lang, "schedule_view_calendar"), callback_data=open_calendar_callback))
            
        elif view_type == 'daily_from_calendar' and date_info: # After picking a date from calendar
            back_to_cal_callback = f"cal_back:{date_info['year']}:{date_info['month']}:{entity_type}:{safe_entity_id}:{date_info['date_str']}"
            
            ical_callback = f"sch_export_ical:{entity_type}:{safe_entity_id}:{date_info['date_str']}"
            builder.row(InlineKeyboardButton(text=translator.gettext(lang, "schedule_export_ical"), callback_data=ical_callback))
            
            builder.row(InlineKeyboardButton(text=translator.gettext(lang, "schedule_back_to_calendar"), callback_data=back_to_cal_callback))
            
        elif view_type == 'weekly' and date_info: # After picking a week
            ical_callback = f"sch_export_ical:{entity_type}:{safe_entity_id}:{date_info['date_str']}"
            builder.row(InlineKeyboardButton(text=translator.gettext(lang, "schedule_export_ical"), callback_data=ical_callback))
            # Also add a button to go back to the calendar view for that month
            back_to_cal_callback = f"cal_back:{date_info['year']}:{date_info['month']}:{entity_type}:{safe_entity_id}:{date_info['date_str']}"
            builder.row(InlineKeyboardButton(text=translator.gettext(lang, "schedule_back_to_calendar"), callback_data=back_to_cal_callback))

        # Back to search results (always relevant)
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "schedule_back_to_results"), callback_data="sch_back_to_results"))
        return builder

    async def handle_date_selection(self, callback: CallbackQuery):
        await callback.answer()
        _, entity_type, entity_id, date_str = callback.data.split(":")
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id, callback.message.chat.id)
        await callback.message.edit_text(translator.gettext(lang, "schedule_loading"))
        try:
            original_entity_id = entity_id
            if len(entity_id) == 16 and not entity_id.isdigit():
                original_entity_id = code_path_cache.get(entity_id, entity_id)

            selected_date = datetime.strptime(date_str, "%Y-%m-%d")
            api_date_str = selected_date.strftime("%Y-%m-%d")

            # --- Fetch Data ---
            schedule_data = []
            cached_full_schedule = await get_cached_schedule(entity_type, original_entity_id)
            if cached_full_schedule:
                schedule_data = [l for l in cached_full_schedule if l['date'] == api_date_str]
            else:
                schedule_data = await self.api_client.get_schedule(entity_type, original_entity_id, start=api_date_str, finish=api_date_str)

            # --- Resolve Name ---
            entity_name = await self._resolve_entity_name(user_id, entity_type, original_entity_id, schedule_data)

            formatted_text = await format_schedule(
                schedule_data=schedule_data,
                lang=lang,
                entity_name=entity_name,
                entity_type=entity_type,
                user_id=user_id,
                start_date=selected_date.date())
            
            await callback.message.edit_text(formatted_text, parse_mode="HTML")
            date_info = {
                'year': selected_date.year,
                'month': selected_date.month,
                'date_str': date_str
            }
            # Передаем entity_id (возможно хэш), чтобы кнопки работали
            await self._send_actions_menu(callback.message, lang, entity_type, entity_id, entity_name, 'daily_from_calendar', date_info)
        except Exception as e:
            logging.error(f"Failed to get schedule for {entity_type}:{entity_id}. Error: {e}", exc_info=True)
            await callback.message.edit_text(translator.gettext(lang, "schedule_api_error"))
            
    async def handle_week_selection(self, callback: CallbackQuery):
        await callback.answer()
        _, entity_type, entity_id, start_date_str = callback.data.split(":")
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id, callback.message.chat.id)
        await callback.message.edit_text(translator.gettext(lang, "schedule_loading"))
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = start_date + timedelta(days=6)
            api_start_str, api_end_str = start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")

            original_entity_id = entity_id
            if len(entity_id) == 16 and not entity_id.isdigit():
                original_entity_id = code_path_cache.get(entity_id, entity_id)

            # --- Fetch Data ---
            schedule_data = []
            cached_full_schedule = await get_cached_schedule(entity_type, original_entity_id)
            if cached_full_schedule:
                schedule_data = [
                    l for l in cached_full_schedule 
                    if start_date <= datetime.strptime(l['date'], "%Y-%m-%d").date() <= end_date
                ]
            else:
                schedule_data = await self.api_client.get_schedule(entity_type, original_entity_id, start=api_start_str, finish=api_end_str)

            # --- Resolve Name ---
            entity_name = await self._resolve_entity_name(user_id, entity_type, original_entity_id, schedule_data)

            formatted_text = await format_schedule(
                schedule_data=schedule_data,
                lang=lang,
                entity_name=entity_name,
                entity_type=entity_type,
                user_id=callback.from_user.id,
                start_date=start_date,
                is_week_view=True)
            
            await callback.message.edit_text(formatted_text, parse_mode="HTML")
            date_info = {
                'year': start_date.year,
                'month': start_date.month,
                'date_str': start_date_str
            }
            await self._send_actions_menu(callback.message, lang, entity_type, entity_id, entity_name, 'weekly', date_info)
        except Exception as e:
            logging.error(f"Failed to get weekly schedule for {entity_type}:{entity_id}. Error: {e}", exc_info=True)
            await callback.message.edit_text(translator.gettext(lang, "schedule_api_error"))
            
    async def _prepare_ical_file(self, user_id: int, entity_type: str, entity_id: str, start_date_str: str) -> tuple[bytes, str, date, date]:
        """Fetches schedule, generates iCal string, and returns file bytes and metadata."""
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = start_date + timedelta(days=6)
        api_start_str, api_end_str = start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
        
        original_entity_id = entity_id
        if len(entity_id) == 16 and not entity_id.isdigit():
            original_entity_id = code_path_cache.get(entity_id, entity_id)

        schedule_data = []
        cached_full_schedule = await get_cached_schedule(entity_type, original_entity_id)
        if cached_full_schedule:
            schedule_data = [
                l for l in cached_full_schedule 
                if start_date <= datetime.strptime(l['date'], "%Y-%m-%d").date() <= end_date
            ]
        else:
            schedule_data = await self.api_client.get_schedule(entity_type, original_entity_id, start=api_start_str, finish=api_end_str)
        
        # --- Resolve Name ---
        entity_name = await self._resolve_entity_name(user_id, entity_type, original_entity_id, schedule_data)
        
        ical_string = generate_ical_from_schedule(schedule_data, entity_name)
        file_bytes = ical_string.encode('utf-8')
        filename = f"schedule_{entity_name.replace(' ', '_')}_{start_date_str}.ics"
        
        return file_bytes, filename, start_date, end_date
    
    async def handle_ical_export(self, callback: CallbackQuery):
        await callback.answer()
        _, entity_type, entity_id, start_date_str = callback.data.split(":")
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id, callback.message.chat.id)
        await callback.message.edit_text(translator.gettext(lang, "schedule_exporting_ical"))
        try:
            file_bytes, filename, start_date, end_date = await self._prepare_ical_file(user_id, entity_type, entity_id, start_date_str)
            await callback.message.answer_document(
                document=BufferedInputFile(file_bytes, filename=filename),
                caption=translator.gettext(lang, "schedule_export_ical_caption", start=start_date.strftime('%d.%m'), end=end_date.strftime('%d.%m'))
            )
            await callback.message.delete()
        except Exception as e:
            logging.error(f"Failed to generate iCal for {entity_type}:{entity_id}. Error: {e}", exc_info=True)
            await callback.message.edit_text(translator.gettext(lang, "schedule_export_ical_error"))

    async def handle_subscribe_button(self, callback: CallbackQuery, state: FSMContext):
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id, callback.message.chat.id)
        try:
            data_hash = callback.data.split(":", 1)[1]
            data_part = code_path_cache.get(data_hash)
            entity_type, entity_id, entity_name = data_part.split(":", 2)
        except (ValueError, TypeError):
            logging.error(f"Invalid subscribe callback data: {callback.data}")
            await callback.answer(translator.gettext(lang, "schedule_subscribe_error"), show_alert=True)
            return
        await state.set_state(ScheduleStates.awaiting_subscription_time)
        await state.update_data(sub_entity_type=entity_type, sub_entity_id=entity_id, sub_entity_name=entity_name)
        await callback.message.edit_text(translator.gettext(lang, "schedule_prompt_for_time"))
        await callback.answer()

    async def handle_subscription_time(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        lang = await translator.get_language(user_id, message.chat.id)
        time_str = message.text.strip()
        if not re.match(r"^\d{2}:\d{2}$", time_str):
            await message.reply(translator.gettext(lang, "schedule_invalid_time_format"))
            return
        try:
            notification_time = time.fromisoformat(time_str)
            chat_id = message.chat.id
            thread_id = message.message_thread_id if message.is_topic_message else None
            sub_data = await state.get_data() # {sub_entity_type, sub_entity_id, sub_entity_name}

            # --- FIX: Prevent "First Run" Notification Spam ---
            # 1. Add the subscription to the DB to get its ID
            sub_id = await database.add_schedule_subscription(
                user_id, chat_id, thread_id, sub_data['sub_entity_type'],
                sub_data['sub_entity_id'], sub_data['sub_entity_name'], notification_time
            )
            # 2. Immediately fetch schedule, hash it, and store it.
            # This "primes" the subscription so the first check doesn't see a change.
            sem_start, sem_end = get_semester_bounds()
            
            logging.info(f"Fetching full semester schedule for subscription: {sub_data['sub_entity_name']} ({sem_start} - {sem_end})")
            
            # Запрашиваем полное расписание
            full_semester_schedule = await self.api_client.get_schedule(
                sub_data['sub_entity_type'], 
                sub_data['sub_entity_id'], 
                start=sem_start, 
                finish=sem_end
            )
            
            # Полностью обновляем кэш (upsert), так как данные семестра самые полные и приоритетные
            await upsert_cached_schedule(sub_data['sub_entity_type'], sub_data['sub_entity_id'], full_semester_schedule)
            
            # 3. Для хеша подписки (чтобы не спамить уведомлениями сразу) берем срез на ближайшие 3 недели, как и было
            start_date = datetime.now()
            end_date = start_date + timedelta(weeks=3)
            
            # Фильтруем из только что полученных полных данных
            schedule_data_for_hash = [
                l for l in full_semester_schedule 
                if start_date.strftime("%Y-%m-%d") <= l['date'] <= end_date.strftime("%Y-%m-%d")
            ]
            
            new_hash = hashlib.sha256(json.dumps(schedule_data_for_hash, sort_keys=True).encode()).hexdigest()
            await database.update_subscription_hash(sub_id, new_hash)
            
            # Redis кэш для diffs (можно оставить, он используется для быстрой проверки изменений)
            await redis_client.set_user_cache(user_id, f"schedule_data:{sub_id}", json.dumps(schedule_data_for_hash), ttl=None)
            
            if sub_data['sub_entity_type'] == 'group':
                unique_modules = await get_unique_modules_hybrid(full_semester_schedule)
                
                if unique_modules:
                    # По умолчанию делаем список ПУСТЫМ (ничего не выбрано)
                    # Или, если хотите, чтобы по умолчанию все были ВКЛЮЧЕНЫ:
                    # current_selected = unique_modules.copy()
                    current_selected = [] 
                    await update_subscription_modules(sub_id, current_selected)
                    
                    keyboard = get_modules_keyboard(unique_modules, current_selected, sub_id)
                    
                    # Отправляем сообщение об успехе + меню настройки
                    await message.answer(
                        translator.gettext(lang, "schedule_subscribe_success", entity_name=sub_data['sub_entity_name'], time_str=time_str) + 
                        "\n\n👇 <b>Внимание:</b> Обнаружены учебные модули. Отметьте те, которые вы посещаете:",
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                    return # Прерываем, чтобы не отправлять стандартное сообщение ниже

            await message.answer(translator.gettext(lang, "schedule_subscribe_success", entity_name=sub_data['sub_entity_name'], time_str=time_str))
        except ValueError:
            await message.reply(translator.gettext(lang, "schedule_invalid_time_value"))
        except Exception as e:
            logging.error(f"Error saving subscription for user {user_id}: {e}", exc_info=True)
            await message.answer(translator.gettext(lang, "schedule_subscribe_dberror"))
        finally:
            await state.clear()

    async def _send_single_schedule_update(self, message: Message, lang: str, sub: dict, today_dt: datetime):
        """Fetches and sends the schedule for a single subscription."""
        user_id = message.from_user.id
        today_str = today_dt.strftime("%Y-%m-%d")
        try:
            # --- NEW: Check local DB cache first ---
            schedule_data = []
            cached_full_schedule = await get_cached_schedule(sub['entity_type'], sub['entity_id'])
            if cached_full_schedule:
                schedule_data = [l for l in cached_full_schedule if l['date'] == today_str]
            else:
                schedule_data = await self.api_client.get_schedule(sub['entity_type'], sub['entity_id'], start=today_str, finish=today_str)

            formatted_text = await format_schedule(
                schedule_data=schedule_data, 
                lang=lang, 
                entity_name=sub['entity_name'], 
                entity_type=sub['entity_type'], 
                user_id=user_id, 
                start_date=today_dt.date(),
                subscription_id=sub['id']
            )
            
            await message.answer(formatted_text, parse_mode="HTML")
        except TelegramForbiddenError:
            logging.warning(f"Bot is blocked by user {user_id}. Cannot send schedule.")
            raise  # Re-raise to stop sending to this user
        except Exception as e:
            logging.error(f"Failed to send schedule to user {user_id} for entity {sub['entity_name']}: {e}", exc_info=True)

    async def cmd_my_schedule(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        lang = await translator.get_language(user_id, message.chat.id)
        
        all_subscriptions, _ = await database.get_user_subscriptions(user_id, page=0, page_size=100)
        active_subscriptions = [sub for sub in all_subscriptions if sub['is_active']]

        if not active_subscriptions:
            await message.answer(translator.gettext(lang, "myschedule_no_subscriptions"))
            return

        status_msg = await message.answer(translator.gettext(lang, "myschedule_loading"))
        today_dt = datetime.now()

        processed_entities = set()
        sent_at_least_one = False

        await status_msg.delete()

        for sub in active_subscriptions:
            entity_key = (sub['entity_type'], sub['entity_id'])
            if entity_key in processed_entities: continue
            try:
                await self._send_single_schedule_update(message, lang, sub, today_dt)
                processed_entities.add(entity_key)
                sent_at_least_one = True
                await asyncio.sleep(0.2)
            except TelegramForbiddenError:
                break

        if not sent_at_least_one:
            await message.answer(translator.gettext(lang, "schedule_no_lessons_today"))
        
        builder = InlineKeyboardBuilder()
        today_str = today_dt.strftime("%Y-%m-%d")
        
        # mysch_ical:{start_date}:{duration_days}
        # Экспортируем только сегодня (1 день), так как команда "на сегодня"
        builder.row(InlineKeyboardButton(text="📲 Экспорт iCal (Сегодня)", callback_data=f"mysch_ical:{today_str}:1"))
        builder.row(InlineKeyboardButton(text="🗓 Открыть полный календарь", callback_data="mysch_open_cal"))
        
        await message.answer("Действия:", reply_markup=builder.as_markup())
            

    async def handle_module_toggle(self, callback: CallbackQuery):
        """
        Обрабатывает нажатие на переключатель модуля.
        Полностью восстанавливает контекст из БД, не полагаясь на RAM.
        """
        try:
            _, sub_id_str, mod_hash = callback.data.split(":")
            sub_id = int(sub_id_str)
        except ValueError:
            await callback.answer("Неверные данные кнопки.", show_alert=True)
            return

        # 1. Получаем данные о подписке, чтобы узнать entity_id
        sub_info = await get_subscription_by_id(sub_id)
        if not sub_info:
            await callback.answer("Подписка не найдена.", show_alert=True)
            await callback.message.delete()
            return

        # 2. Получаем расписание из кэша, чтобы восстановить список ВСЕХ модулей
        # (Нам нужно найти полное имя модуля по его хэшу)
        full_schedule = await get_cached_schedule(sub_info['entity_type'], sub_info['entity_id'])
        if not full_schedule:
            await callback.answer("Расписание устарело, попробуйте подписаться заново.", show_alert=True)
            return

        available_modules = await get_unique_modules_hybrid(full_schedule)
        
        # 3. Ищем, какому модулю соответствует хэш из кнопки
        target_module_name = None
        for mod in available_modules:
            if hashlib.md5(mod.encode()).hexdigest()[:8] == mod_hash:
                target_module_name = mod
                break
        
        if not target_module_name:
            await callback.answer("Модуль не найден (возможно, изменилось расписание).", show_alert=True)
            return

        # 4. Получаем текущий выбор пользователя из БД
        selected_modules = await get_subscription_modules(sub_id)
        
        # 5. Переключаем состояние
        if target_module_name in selected_modules:
            selected_modules.remove(target_module_name)
            action_text = "скрыт"
        else:
            selected_modules.append(target_module_name)
            action_text = "выбран"

        # 6. Сохраняем в БД
        await update_subscription_modules(sub_id, selected_modules)

        # 7. Обновляем клавиатуру
        # Мы используем available_modules (полученные на шаге 2) и новый selected_modules
        new_keyboard = get_modules_keyboard(available_modules, selected_modules, sub_id)
        
        # try-except нужен, так как Telegram ругается, если клавиатура визуально не изменилась
        try:
            await callback.message.edit_reply_markup(reply_markup=new_keyboard)
        except Exception:
            pass 
            
        await callback.answer(f"Модуль '{target_module_name}' {action_text}.")

    async def handle_module_save(self, callback: CallbackQuery):
        """Завершает настройку модулей."""
        _, sub_id_str = callback.data.split(":")
        sub_id = int(sub_id_str)
        
        # Можно получить итоговый список, чтобы показать пользователю
        selected = await get_subscription_modules(sub_id)
        count = len(selected)
        
        await callback.message.delete()
        
        if count == 0:
            msg = "⚠️ Вы не выбрали ни одного модуля. Будут показываться только общие предметы."
        else:
            msg = f"✅ Настройки сохранены! Выбрано модулей: {count}. Расписание будет фильтроваться."
            
        await callback.message.answer(msg)
        await callback.answer()
        
    async def _get_user_filters(self, user_id: int) -> dict:
        """Получает фильтры из Redis. Если нет - возвращает пустые (показывать всё)."""
        raw = await redis_client.get_user_cache(user_id, "mysch_filters")
        if raw:
            return raw
        return {'excluded_subs': [], 'excluded_types': []}
    
    async def _save_user_filters(self, user_id: int, filters: dict):
        await redis_client.set_user_cache(user_id, "mysch_filters", filters, ttl=3600)
    
    async def _render_calendar(self, callback: CallbackQuery, year: int, month: int):
        """Рендерит календарь с учетом данных."""
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id)
        
        # 1. Получаем подписки и фильтры
        subs, _ = await database.get_user_subscriptions(user_id, page=0, page_size=100)
        active_subs = [s for s in subs if s['is_active']]
        filters = await self._get_user_filters(user_id)

        # 2. Определяем диапазон дат (весь месяц)
        num_days = calendar.monthrange(year, month)[1]
        start_date = date(year, month, 1)
        end_date = date(year, month, num_days)

        # 3. Агрегируем данные
        schedule = await get_aggregated_schedule(user_id, active_subs, start_date, end_date, filters)

        # 4. Вычисляем маркеры занятости
        busy_days = {}
        for lesson in schedule:
            try:
                l_date = datetime.strptime(lesson['date'], "%Y-%m-%d").date()
                day = l_date.day
                
                # Приоритет маркеров: Экзамен (!) > Обычная пара (•)
                kind = lesson.get('kindOfWork', '').lower()
                is_exam = 'экзамен' in kind or 'аттестация' in kind or 'зачет' in kind
                
                if is_exam:
                    busy_days[day] = "❗️"
                elif day not in busy_days:
                    busy_days[day] = "•"
            except:
                pass

        keyboard = get_myschedule_calendar_keyboard(year, month, lang, busy_days)
        
        # Сохраняем текущий "просматриваемый месяц" в Redis, чтобы кнопка "Назад" из фильтров знала куда вернуться
        await redis_client.set_user_cache(user_id, "mysch_current_view", {'year': year, 'month': month})

        try:
            await callback.message.edit_text(f"📅 Календарь на {start_date.strftime('%B %Y')}", reply_markup=keyboard)
        except:
            pass # ignore 'message not modified'
        
    async def handle_myschedule_open(self, callback: CallbackQuery):
        now = datetime.now()
        await self._render_calendar(callback, now.year, now.month)
        await callback.answer()
        

    async def handle_myschedule_nav(self, callback: CallbackQuery):
        _, action, y_str, m_str = callback.data.split(":")
        year, month = int(y_str), int(m_str)
        
        if action == 'prev':
            month -= 1
            if month < 1: month = 12; year -= 1
        elif action == 'next':
            month += 1
            if month > 12: month = 1; year += 1
        elif action == 'today':
            now = datetime.now()
            year, month = now.year, now.month

        await self._render_calendar(callback, year, month)
        await callback.answer()
        

    async def handle_myschedule_day(self, callback: CallbackQuery):
        _, y_str, m_str, d_str = callback.data.split(":")
        target_date = date(int(y_str), int(m_str), int(d_str))
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id)

        subs, _ = await database.get_user_subscriptions(user_id, page=0, page_size=100)
        active_subs = [s for s in subs if s['is_active']]
        filters = await self._get_user_filters(user_id)
        
        schedule = await get_aggregated_schedule(user_id, active_subs, target_date, target_date, filters)

        if not schedule:
            await callback.answer("На этот день занятий нет (с учетом фильтров).", show_alert=True)

        formatted_lessons = []
        for l in schedule:
            l_copy = l.copy()
            l_copy['lecturer_title'] = f"{l_copy.get('lecturer_title','')} ({l.get('source_entity')})"
            formatted_lessons.append(l_copy)

        if not schedule:
            text = f"Сводка на {target_date.strftime('%d.%m')}:\n\nЗанятий нет."
        else:
            text = await format_schedule(formatted_lessons, lang, f"Сводка на {target_date.strftime('%d.%m')}", "mixed", user_id, target_date)
        
        builder = InlineKeyboardBuilder()
        
        date_str = target_date.strftime("%Y-%m-%d")
        builder.row(InlineKeyboardButton(text="📲 Экспорт iCal", callback_data=f"mysch_ical:{date_str}:1"))
        
        builder.row(InlineKeyboardButton(text="⬅️ Назад к календарю", callback_data="mysch_back_cal"))
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()

    async def handle_myschedule_filters_menu(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        filters = await self._get_user_filters(user_id)
        subs, _ = await database.get_user_subscriptions(user_id, page=0, page_size=100)
        active_subs = [s for s in subs if s['is_active']]
        
        kb = get_myschedule_filters_keyboard(filters, active_subs)
        await callback.message.edit_text("⚙️ Настройка отображения:", reply_markup=kb)
        await callback.answer()

    async def handle_myschedule_toggle_filter(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        filters = await self._get_user_filters(user_id)
        data_parts = callback.data.split(":")
        action_type = data_parts[0] # mysch_tog_type или mysch_tog_sub
        value = data_parts[1]

        if action_type == "mysch_tog_type":
            target_list = filters['excluded_types']
            if value in target_list: target_list.remove(value)
            else: target_list.append(value)
        
        elif action_type == "mysch_tog_sub":
            sub_id = int(value)
            target_list = filters['excluded_subs']
            if sub_id in target_list: target_list.remove(sub_id)
            else: target_list.append(sub_id)

        await self._save_user_filters(user_id, filters)
        
        # Обновляем меню
        subs, _ = await database.get_user_subscriptions(user_id, page=0, page_size=100)
        active_subs = [s for s in subs if s['is_active']]
        kb = get_myschedule_filters_keyboard(filters, active_subs)
        
        try:
            await callback.message.edit_reply_markup(reply_markup=kb)
        except: pass
        await callback.answer()

    async def handle_myschedule_back_to_cal(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        # Восстанавливаем состояние (год/месяц)
        state = await redis_client.get_user_cache(user_id, "mysch_current_view")
        if state:
            year, month = state['year'], state['month']
        else:
            now = datetime.now()
            year, month = now.year, now.month
            
        await self._render_calendar(callback, year, month)
        
    async def handle_myschedule_week(self, callback: CallbackQuery):
        _, start_date_str = callback.data.split(":")
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = start_date + timedelta(days=6)
        
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id)
        
        await callback.message.edit_text("⏳ Формирую сводку на неделю...")

        subs, _ = await database.get_user_subscriptions(user_id, page=0, page_size=100)
        active_subs = [s for s in subs if s['is_active']]
        filters = await self._get_user_filters(user_id)
        
        schedule = await get_aggregated_schedule(user_id, active_subs, start_date, end_date, filters)
        
        # Форматирование
        formatted_lessons = []
        for l in schedule:
            l_copy = l.copy()
            # Добавляем источник в преподавателя (или можно в аудиторию), чтобы видеть откуда пара
            l_copy['lecturer_title'] = f"{l_copy.get('lecturer_title','')} ({l.get('source_entity')})"
            formatted_lessons.append(l_copy)
            
        header = f"Сводка: {start_date.strftime('%d.%m')} - {end_date.strftime('%d.%m')}"
        
        # Используем format_schedule с is_week_view=True
        text = await format_schedule(formatted_lessons, lang, header, "mixed", user_id, start_date, is_week_view=True)
        
        # Если текст слишком длинный, format_schedule вернет длинную строку. Aiogram сам разобьет при отправке? 
        # Нет, edit_text упадет если > 4096.
        # Для простоты, если очень длинно, обрезаем или предупреждаем.
        if len(text) > 4000:
            text = text[:4000] + "\n\n...(сообщение обрезано, слишком много пар)..."

        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="📲 Экспорт iCal (Неделя)", callback_data=f"mysch_ical:{start_date_str}:7"))
        builder.row(InlineKeyboardButton(text="⬅️ Назад к календарю", callback_data="mysch_back_cal"))
        
        try:
            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception as e:
            # Fallback if text is problematic
            await callback.message.answer_document(
                BufferedInputFile(text.encode('utf-8'), filename="schedule.txt"),
                caption="Текст расписания слишком длинный для одного сообщения.",
                reply_markup=builder.as_markup()
            )
        await callback.answer()

    async def handle_myschedule_export_ical(self, callback: CallbackQuery):
        """
        Generates and sends an iCal file for aggregated schedule.
        Data format: mysch_ical:YYYY-MM-DD:days_count
        """
        try:
            _, start_date_str, days_count_str = callback.data.split(":")
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            days_count = int(days_count_str)
            end_date = start_date + timedelta(days=days_count - 1) # if 1 day, end = start
        except ValueError:
            await callback.answer("Ошибка данных.", show_alert=True)
            return

        user_id = callback.from_user.id
        lang = await translator.get_language(user_id)
        
        await callback.answer("Генерация файла...")
        
        # 1. Get Data
        subs, _ = await database.get_user_subscriptions(user_id, page=0, page_size=100)
        active_subs = [s for s in subs if s['is_active']]
        filters = await self._get_user_filters(user_id)
        
        schedule = await get_aggregated_schedule(user_id, active_subs, start_date, end_date, filters)
        
        if not schedule:
            await callback.message.answer("Нет занятий для экспорта.")
            return

        # 2. Generate ICS
        ical_data = generate_ical_from_aggregated_schedule(schedule)
        
        # 3. Send
        filename = f"myschedule_{start_date_str}_{days_count}days.ics"
        caption = translator.gettext(lang, "schedule_export_ical_caption", start=start_date.strftime('%d.%m'), end=end_date.strftime('%d.%m'))
        
        await callback.message.answer_document(
            document=BufferedInputFile(ical_data.encode('utf-8'), filename=filename),
            caption=caption
        )
        
    async def _resolve_entity_name(self, user_id: int, entity_type: str, entity_id: str, schedule_data: list = None) -> str:
        """
        Пытается найти человекочитаемое название (напр. 'ПМ23-1') по ID.
        Порядок поиска:
        1. Кэш текущего поиска (Redis)
        2. История поиска (Redis)
        3. Подписки пользователя (DB)
        4. Данные самого расписания (из первого урока)
        """
        # 1. Проверяем кэш текущего поиска
        cached_search = await redis_client.get_user_cache(user_id, 'schedule_search')
        if cached_search and cached_search.get('results'):
            item = next((i for i in cached_search['results'] if str(i['id']) == str(entity_id)), None)
            if item: return item['label']

        # 2. Проверяем историю поиска
        history_key = f"schedule_history:{user_id}"
        history_raw = await redis_client.client.lrange(history_key, 0, -1)
        for item_json in history_raw:
            try:
                item = json.loads(item_json)
                if str(item.get('entity_id')) == str(entity_id) and item.get('entity_type') == entity_type:
                    return item['entity_name']
            except: continue

        # 3. Проверяем подписки
        subs, _ = await database.get_user_subscriptions(user_id, page=0, page_size=100)
        sub = next((s for s in subs if str(s['entity_id']) == str(entity_id) and s['entity_type'] == entity_type), None)
        if sub: return sub['entity_name']

        # 4. Пытаемся извлечь из данных расписания (если переданы)
        if schedule_data and len(schedule_data) > 0:
            lesson = schedule_data[0]
            if entity_type == 'group':
                return lesson.get('group', 'Unknown')
            elif entity_type == 'person':
                return lesson.get('lecturer_title', 'Unknown')
            elif entity_type == 'auditorium':
                return lesson.get('auditorium', 'Unknown')

        return "Unknown"
    
    async def _send_cal_link_message(self, message: Message, user_id: int, is_edit: bool = False):
        """Отправляет или редактирует сообщение с инструкцией и ссылкой на WebCal."""
        secret = await database.get_or_create_calendar_secret(user_id)
        
        from bot.config import PUBLIC_API_URL
        base_url = PUBLIC_API_URL.rstrip('/')
        http_link = f"{base_url}/api/cal/{secret}.ics"
        webcal_link = http_link.replace("https://", "webcal://").replace("http://", "webcal://")

        text = (
            "🔗 <b>Ваша персональная ссылка на расписание</b>\n\n"
            f"<code>{http_link}</code>\n\n"
            "<b>Как добавить, чтобы оно обновлялось само:</b>\n"
            "• <b>iOS (iPhone/Mac):</b> Нажмите кнопку ниже. Если не сработает, то Настройки -> Календарь -> Учетные записи -> Добавить -> Другое -> Календарь по подписке.\n"
            "• <b>Google Calendar:</b> Откройте <u>веб-версию (на ПК)</u>, нажмите «+» рядом с «Другие календари» -> «Добавить по URL» и вставьте ссылку выше.\n\n"
            "<i>Расписание выгружается на 3 месяца вперед и обновляется автоматически.</i>"
        )

        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="📱 Добавить на iOS / Mac", url=webcal_link))
        builder.row(InlineKeyboardButton(text="🔄 Сбросить ссылку", callback_data="mysch_cal_revoke"))
        builder.row(InlineKeyboardButton(text="⬅️ Назад в календарь", callback_data="mysch_back_cal"))

        if is_edit:
            await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

    async def handle_cal_link(self, callback: CallbackQuery):
        await self._send_cal_link_message(callback.message, callback.from_user.id, is_edit=True)
        await callback.answer()

    async def handle_cal_revoke(self, callback: CallbackQuery):
        await database.regenerate_calendar_secret(callback.from_user.id)
        await callback.answer("Ссылка обновлена. Старая больше не работает и отключена.", show_alert=True)
        await self._send_cal_link_message(callback.message, callback.from_user.id, is_edit=True)
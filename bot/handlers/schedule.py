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
    update_subscription_modules,
    get_subscription_modules,
    get_subscription_by_id,
    get_user_subscriptions,
    get_user_settings,
    search_cached_entities,
    get_session
)
from shared_lib.services.schedule_service import (
    format_schedule, 
    generate_ical_from_schedule,
    get_semester_bounds,
    get_unique_modules_hybrid,
    generate_ical_from_aggregated_schedule,
    get_module_name,
    get_aggregated_schedule,
    generate_module_details_text,
    get_schedule_with_cache_fallback
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

        history_key = f"schedule_history:{user_id}"
        history_items_raw = await redis_client.client.lrange(history_key, 0, -1)
        history_items =[json.loads(item) for item in history_items_raw]

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
        except asyncio.TimeoutError:
            results = None # Перехватим ниже
        except Exception as e:
            logging.warning(f"RUZ API Search failed in bot: {e}. Trying fallback to cache.")
            results = None
            
        # Если API не справилось, достаем данные из нашей базы
        if not results:
            async with get_session() as db:
                results = await search_cached_entities(db, query, search_type)

        if not results:
            await message.answer(translator.gettext(lang, "schedule_no_results", query=query))
            await status_msg.delete()
            return
            
        # Если это оффлайн результаты, предупреждаем пользователя сообщением
        if any(r.get("is_offline") for r in results):
            await message.answer("⚠️ <i>Нет связи с вузом. Показаны сохраненные копии из базы.</i>", parse_mode="HTML")

        await redis_client.set_user_cache(user_id, 'schedule_search', {'query': query, 'search_type': search_type, 'results': results})
        keyboard = build_search_results_keyboard(results, search_type)
        await message.answer(translator.gettext(lang, "schedule_results_found", count=len(results)), reply_markup=keyboard)
        await status_msg.delete()

    async def handle_search_query(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        lang = await translator.get_language(user_id, message.chat.id)
        if not message.text:
            await message.reply(translator.gettext(lang, "schedule_invalid_time_format")) 
            return

        data = await state.get_data()
        search_type = data['search_type']
        query = message.text.lower()
        await state.clear()

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

            # --- ИСПОЛЬЗУЕМ УМНЫЙ ФЕТЧЕР ---
            try:
                schedule_data, is_offline = await get_schedule_with_cache_fallback(
                    self.api_client, entity_type, entity_id, api_date_str, api_date_str
                )
            except ConnectionError:
                error_msg = "❌ ВУЗ недоступен, а сохраненной копии расписания у меня пока нет. Попробуйте позже." if lang == 'ru' else "❌ University server is down and I have no cached copy. Please try again later."
                await callback.message.edit_text(error_msg)
                return

            entity_name = await self._resolve_entity_name(user_id, entity_type, entity_id, schedule_data)
            
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
            
            if is_offline:
                offline_warning = "⚠️ <i>Нет связи с сервером ВУЗа. Показана последняя сохраненная копия.</i>\n\n" if lang == 'ru' else "⚠️ <i>No connection to university server. Showing latest cached copy.</i>\n\n"
                formatted_text = offline_warning + formatted_text

            await callback.message.edit_text(formatted_text, parse_mode="HTML")
            await self._send_actions_menu(callback.message, lang, entity_type, entity_id, entity_name, view_type='daily_initial')
        except Exception as e:
            logging.error(f"Failed to get today's schedule for {entity_type}:{entity_id}. Error: {e}", exc_info=True)
            await callback.message.edit_text(translator.gettext(lang, "schedule_api_error"))
            
    async def handle_history_selection(self, callback: CallbackQuery, state: FSMContext):
        new_data = callback.data.replace("sch_history:", "sch_result_:")
        modified_callback = callback.model_copy(update={'data': new_data})
        await self.handle_result_selection(modified_callback, state)

    async def handle_clear_history(self, callback: CallbackQuery, state: FSMContext):
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id, callback.message.chat.id)
        history_key = f"schedule_history:{user_id}"
        await redis_client.client.delete(history_key)

        keyboard = await get_schedule_type_keyboard(lang, history_items=[])
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        await callback.answer(translator.gettext(lang, "schedule_history_cleared"))

    async def handle_open_calendar(self, callback: CallbackQuery):
        await callback.answer()
        _, entity_type, entity_id = callback.data.split(":")
        lang = await translator.get_language(callback.from_user.id, callback.message.chat.id)
        now = datetime.now()

        if len(entity_id) > 32:
            id_hash = hashlib.sha1(entity_id.encode()).hexdigest()[:16]
            code_path_cache[id_hash] = entity_id
            entity_id_for_callback = id_hash
        else:
            entity_id_for_callback = entity_id

        calendar_keyboard = build_calendar_keyboard(now.year, now.month, entity_type, entity_id_for_callback, lang)
        await callback.message.edit_text(translator.gettext(lang, "schedule_select_date"), reply_markup=calendar_keyboard)

    async def handle_calendar_navigation(self, callback: CallbackQuery):
        await callback.answer()
        try:
            _, action, year_str, month_str, entity_type, entity_id = callback.data.split(":")
            year, month = int(year_str), int(month_str)

            if len(entity_id) == 16 and not entity_id.isdigit():
                pass 

            if action == "prev_month": month -= 1; year = year - 1 if month == 0 else year; month = 12 if month == 0 else month
            elif action == "next_month": month += 1; year = year + 1 if month == 13 else year; month = 1 if month == 13 else month
            elif action == "prev_year": year -= 1
            elif action == "next_year": year += 1
            elif action == "today":
                now = datetime.now()
                if now.year == int(year_str) and now.month == int(month_str):
                    await callback.answer(translator.gettext(await translator.get_language(callback.from_user.id, callback.message.chat.id), "calendar_already_on_today"), show_alert=False)
                    return
                year, month = now.year, now.month

            lang = await translator.get_language(callback.from_user.id, callback.message.chat.id)
            try:
                await callback.message.edit_reply_markup(reply_markup=build_calendar_keyboard(year, month, entity_type, entity_id, lang))
            except TelegramBadRequest as e:
                if "message is not modified" in e.message:
                    await callback.answer(translator.gettext(lang, "calendar_already_on_today"), show_alert=False)
                else:
                    raise 
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

            if len(entity_id) == 16 and not entity_id.isdigit():
                pass 

            selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()
            lang = await translator.get_language(callback.from_user.id, callback.message.chat.id)
            calendar_keyboard = build_calendar_keyboard(year, month, entity_type, entity_id, lang, selected_date=selected_date)
            await callback.message.edit_text(translator.gettext(lang, "schedule_select_date"), reply_markup=calendar_keyboard)
        except (ValueError, IndexError) as e:
            logging.error(f"Error handling back to calendar navigation: {e}. Data: {callback.data}")

    async def _send_actions_menu(self, message: Message, lang: str, entity_type: str, entity_id: str, entity_name: str, view_type: str, date_info: dict = None):
        keyboard = self._build_schedule_actions_keyboard(lang, entity_type, entity_id, entity_name, view_type, date_info)
        await message.answer(
            translator.gettext(lang, "schedule_actions_prompt"),
            reply_markup=keyboard.as_markup()
        )

    def _build_schedule_actions_keyboard(self, lang: str, entity_type: str, entity_id: str, entity_name: str, view_type: str, date_info: dict | None = None) -> InlineKeyboardBuilder:
        builder = InlineKeyboardBuilder()
        
        subscribe_button_data = build_search_results_keyboard([{'label': translator.gettext(lang, "schedule_subscribe_button"), 'id': f"{entity_type}:{entity_id}:{entity_name}"}], 'subscribe'
        )
        builder.row(subscribe_button_data.inline_keyboard[0][0])

        safe_entity_id = entity_id
        if len(entity_id) > 20: 
            id_hash = hashlib.sha1(entity_id.encode()).hexdigest()[:16]
            code_path_cache[id_hash] = entity_id
            safe_entity_id = id_hash

        if view_type == 'daily_initial': 
            open_calendar_callback = f"sch_open_calendar:{entity_type}:{safe_entity_id}"
            today_str = datetime.now().strftime("%Y-%m-%d")
            ical_callback = f"sch_export_ical:{entity_type}:{safe_entity_id}:{today_str}"
            
            builder.row(InlineKeyboardButton(text=translator.gettext(lang, "schedule_export_ical"), callback_data=ical_callback))
            builder.row(InlineKeyboardButton(text=translator.gettext(lang, "schedule_view_calendar"), callback_data=open_calendar_callback))
            
        elif view_type == 'daily_from_calendar' and date_info:
            back_to_cal_callback = f"cal_back:{date_info['year']}:{date_info['month']}:{entity_type}:{safe_entity_id}:{date_info['date_str']}"
            
            ical_callback = f"sch_export_ical:{entity_type}:{safe_entity_id}:{date_info['date_str']}"
            builder.row(InlineKeyboardButton(text=translator.gettext(lang, "schedule_export_ical"), callback_data=ical_callback))
            builder.row(InlineKeyboardButton(text=translator.gettext(lang, "schedule_back_to_calendar"), callback_data=back_to_cal_callback))
            
        elif view_type == 'weekly' and date_info: 
            ical_callback = f"sch_export_ical:{entity_type}:{safe_entity_id}:{date_info['date_str']}"
            builder.row(InlineKeyboardButton(text=translator.gettext(lang, "schedule_export_ical"), callback_data=ical_callback))
            back_to_cal_callback = f"cal_back:{date_info['year']}:{date_info['month']}:{entity_type}:{safe_entity_id}:{date_info['date_str']}"
            builder.row(InlineKeyboardButton(text=translator.gettext(lang, "schedule_back_to_calendar"), callback_data=back_to_cal_callback))

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

            # --- ИСПОЛЬЗУЕМ УМНЫЙ ФЕТЧЕР ---
            try:
                schedule_data, is_offline = await get_schedule_with_cache_fallback(
                    self.api_client, entity_type, original_entity_id, api_date_str, api_date_str
                )
            except ConnectionError:
                error_msg = "❌ ВУЗ недоступен, а сохраненной копии расписания у меня пока нет. Попробуйте позже." if lang == 'ru' else "❌ University server is down and I have no cached copy. Please try again later."
                await callback.message.edit_text(error_msg)
                return

            entity_name = await self._resolve_entity_name(user_id, entity_type, original_entity_id, schedule_data)

            formatted_text = await format_schedule(
                schedule_data=schedule_data,
                lang=lang,
                entity_name=entity_name,
                entity_type=entity_type,
                user_id=user_id,
                start_date=selected_date.date())
            
            if is_offline:
                offline_warning = "⚠️ <i>Нет связи с сервером ВУЗа. Показана последняя сохраненная копия.</i>\n\n" if lang == 'ru' else "⚠️ <i>No connection to university server. Showing latest cached copy.</i>\n\n"
                formatted_text = offline_warning + formatted_text
            
            await callback.message.edit_text(formatted_text, parse_mode="HTML")
            date_info = {
                'year': selected_date.year,
                'month': selected_date.month,
                'date_str': date_str
            }
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

            # --- ИСПОЛЬЗУЕМ УМНЫЙ ФЕТЧЕР ---
            try:
                schedule_data, is_offline = await get_schedule_with_cache_fallback(
                    self.api_client, entity_type, original_entity_id, api_start_str, api_end_str
                )
            except ConnectionError:
                error_msg = "❌ ВУЗ недоступен, а сохраненной копии расписания у меня пока нет. Попробуйте позже." if lang == 'ru' else "❌ University server is down and I have no cached copy. Please try again later."
                await callback.message.edit_text(error_msg)
                return

            entity_name = await self._resolve_entity_name(user_id, entity_type, original_entity_id, schedule_data)

            formatted_text = await format_schedule(
                schedule_data=schedule_data,
                lang=lang,
                entity_name=entity_name,
                entity_type=entity_type,
                user_id=callback.from_user.id,
                start_date=start_date,
                is_week_view=True)
            
            if is_offline:
                offline_warning = "⚠️ <i>Нет связи с сервером ВУЗа. Показана последняя сохраненная копия.</i>\n\n" if lang == 'ru' else "⚠️ <i>No connection to university server. Showing latest cached copy.</i>\n\n"
                formatted_text = offline_warning + formatted_text
            
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

        try:
            schedule_data, _ = await get_schedule_with_cache_fallback(
                self.api_client, entity_type, original_entity_id, api_start_str, api_end_str
            )
        except ConnectionError:
            schedule_data =[]
        
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
            sub_data = await state.get_data() 

            sub_id = await database.add_schedule_subscription(
                user_id, chat_id, thread_id, sub_data['sub_entity_type'],
                sub_data['sub_entity_id'], sub_data['sub_entity_name'], notification_time
            )
            
            sem_start, sem_end = get_semester_bounds()
            logging.info(f"Fetching full semester schedule for subscription: {sub_data['sub_entity_name']} ({sem_start} - {sem_end})")
            
            full_semester_schedule = await self.api_client.get_schedule(
                sub_data['sub_entity_type'], 
                sub_data['sub_entity_id'], 
                start=sem_start, 
                finish=sem_end
            )
            
            await upsert_cached_schedule(sub_data['sub_entity_type'], sub_data['sub_entity_id'], full_semester_schedule)
            
            start_date = datetime.now()
            end_date = start_date + timedelta(weeks=3)
            
            schedule_data_for_hash =[
                l for l in full_semester_schedule 
                if start_date.strftime("%Y-%m-%d") <= l['date'] <= end_date.strftime("%Y-%m-%d")
            ]
            
            new_hash = hashlib.sha256(json.dumps(schedule_data_for_hash, sort_keys=True).encode()).hexdigest()
            await database.update_subscription_hash(sub_id, new_hash)
            
            await redis_client.set_user_cache(user_id, f"schedule_data:{sub_id}", json.dumps(schedule_data_for_hash), ttl=None)
            
            webcal_btn = InlineKeyboardButton(text=translator.gettext(lang, "kb_cal_webcal_button"), callback_data="mysch_cal_link")
            
            if sub_data['sub_entity_type'] == 'group':
                unique_modules = await get_unique_modules_hybrid(full_semester_schedule)
                
                if unique_modules:
                    current_selected =[] 
                    await update_subscription_modules(sub_id, current_selected)
                    
                    base_keyboard = await get_modules_keyboard(unique_modules, current_selected, sub_id)
                    builder = InlineKeyboardBuilder.from_markup(base_keyboard)
                    builder.row(webcal_btn)
                    
                    settings = await get_user_settings(user_id)
                    details_text = ""
                    if settings.get('show_module_details', True):
                        details_text = generate_module_details_text(full_semester_schedule, lang)
                        
                    await message.answer(
                        translator.gettext(lang, "schedule_subscribe_success", entity_name=sub_data['sub_entity_name'], time_str=time_str) + 
                        "\n\n👇 <b>Внимание:</b> Обнаружены учебные модули. Отметьте те, которые вы посещаете:\n" + 
                        details_text, 
                        reply_markup=builder.as_markup(),
                        parse_mode="HTML"
                    )
                    return 

            builder = InlineKeyboardBuilder()
            builder.row(webcal_btn)
            await message.answer(
                translator.gettext(lang, "schedule_subscribe_success", entity_name=sub_data['sub_entity_name'], time_str=time_str),
                reply_markup=builder.as_markup()
            )
        except ValueError:
            await message.reply(translator.gettext(lang, "schedule_invalid_time_value"))
        except Exception as e:
            logging.error(f"Error saving subscription for user {user_id}: {e}", exc_info=True)
            await message.answer(translator.gettext(lang, "schedule_subscribe_dberror"))
        finally:
            await state.clear()

    async def _send_single_schedule_update(self, message: Message, lang: str, sub: dict, today_dt: datetime):
        user_id = message.from_user.id
        today_str = today_dt.strftime("%Y-%m-%d")
        try:
            # --- ИСПОЛЬЗУЕМ УМНЫЙ ФЕТЧЕР ---
            try:
                schedule_data, is_offline = await get_schedule_with_cache_fallback(
                    self.api_client, sub['entity_type'], sub['entity_id'], today_str, today_str
                )
            except ConnectionError:
                logging.warning(f"Could not update schedule for {sub['entity_name']}: API down & no cache.")
                return

            formatted_text = await format_schedule(
                schedule_data=schedule_data, 
                lang=lang, 
                entity_name=sub['entity_name'], 
                entity_type=sub['entity_type'], 
                user_id=user_id, 
                start_date=today_dt.date(),
                subscription_id=sub['id']
            )
            
            if is_offline:
                offline_warning = "⚠️ <i>Нет связи с сервером ВУЗа. Показана последняя сохраненная копия.</i>\n\n" if lang == 'ru' else "⚠️ <i>No connection to university server. Showing latest cached copy.</i>\n\n"
                formatted_text = offline_warning + formatted_text
            
            await message.answer(formatted_text, parse_mode="HTML")
        except TelegramForbiddenError:
            logging.warning(f"Bot is blocked by user {user_id}. Cannot send schedule.")
            raise  
        except Exception as e:
            logging.error(f"Failed to send schedule to user {user_id} for entity {sub['entity_name']}: {e}", exc_info=True)

    async def cmd_my_schedule(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        lang = await translator.get_language(user_id, message.chat.id)
        
        all_subscriptions, _ = await database.get_user_subscriptions(user_id, page=0, page_size=100)
        active_subscriptions =[sub for sub in all_subscriptions if sub['is_active']]

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
        
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "myschedule_ical_today_button"), callback_data=f"mysch_ical:{today_str}:1"))
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "myschedule_full_calendar_button"), callback_data="mysch_open_cal"))
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "kb_cal_webcal_button"), callback_data="mysch_cal_link"))
        
        await message.answer(translator.gettext(lang, "myschedule_actions_header"), reply_markup=builder.as_markup())
            
    async def handle_module_toggle(self, callback: CallbackQuery):
        try:
            _, sub_id_str, mod_hash = callback.data.split(":")
            sub_id = int(sub_id_str)
        except ValueError:
            await callback.answer("Неверные данные кнопки.", show_alert=True)
            return

        sub_info = await get_subscription_by_id(sub_id)
        if not sub_info:
            await callback.answer("Подписка не найдена.", show_alert=True)
            await callback.message.delete()
            return

        full_schedule = await get_cached_schedule(sub_info['entity_type'], sub_info['entity_id'])
        if not full_schedule:
            await callback.answer("Расписание устарело, попробуйте подписаться заново.", show_alert=True)
            return

        available_modules = await get_unique_modules_hybrid(full_schedule)
        
        target_module_name = None
        for mod in available_modules:
            if hashlib.md5(mod.encode()).hexdigest()[:8] == mod_hash:
                target_module_name = mod
                break
        
        if not target_module_name:
            await callback.answer("Модуль не найден (возможно, изменилось расписание).", show_alert=True)
            return

        selected_modules = await get_subscription_modules(sub_id)
        
        if target_module_name in selected_modules:
            selected_modules.remove(target_module_name)
            action_text = "скрыт"
        else:
            selected_modules.append(target_module_name)
            action_text = "выбран"

        await update_subscription_modules(sub_id, selected_modules)

        new_keyboard = await get_modules_keyboard(available_modules, selected_modules, sub_id)
        
        try:
            await callback.message.edit_reply_markup(reply_markup=new_keyboard)
        except Exception:
            pass 
            
        await callback.answer(f"Модуль '{target_module_name}' {action_text}.")

    async def handle_module_save(self, callback: CallbackQuery):
        _, sub_id_str = callback.data.split(":")
        sub_id = int(sub_id_str)
        
        selected = await get_subscription_modules(sub_id)
        count = len(selected)
        
        await callback.message.delete()
        lang = await translator.get_language(callback.from_user.id) 

        if count == 0:
            msg = translator.gettext(lang, "module_save_no_modules") 
        else:
            msg = translator.gettext(lang, "module_save_success", count=count) 
            
        await callback.message.answer(msg)
        await callback.answer()
        
    async def _get_user_filters(self, user_id: int) -> dict:
        raw = await redis_client.get_user_cache(user_id, "mysch_filters")
        if raw:
            return raw
        return {'excluded_subs': [], 'excluded_types':[]}
    
    async def _save_user_filters(self, user_id: int, filters: dict):
        await redis_client.set_user_cache(user_id, "mysch_filters", filters, ttl=3600)
    
    async def _render_calendar(self, callback: CallbackQuery, year: int, month: int):
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id)
        
        subs, _ = await database.get_user_subscriptions(user_id, page=0, page_size=100)
        active_subs = [s for s in subs if s['is_active']]
        filters = await self._get_user_filters(user_id)

        num_days = calendar.monthrange(year, month)[1]
        start_date = date(year, month, 1)
        end_date = date(year, month, num_days)

        schedule = await get_aggregated_schedule(user_id, active_subs, start_date, end_date, filters)

        busy_days = {}
        for lesson in schedule:
            try:
                l_date = datetime.strptime(lesson['date'], "%Y-%m-%d").date()
                day = l_date.day
                
                kind = lesson.get('kindOfWork', '').lower()
                is_exam = 'экзамен' in kind or 'аттестация' in kind or 'зачет' in kind
                
                if is_exam:
                    busy_days[day] = "❗️"
                elif day not in busy_days:
                    busy_days[day] = "•"
            except:
                pass

        keyboard = get_myschedule_calendar_keyboard(year, month, lang, busy_days)
        
        await redis_client.set_user_cache(user_id, "mysch_current_view", {'year': year, 'month': month})

        try:
            await callback.message.edit_text(f"📅 Календарь на {start_date.strftime('%B %Y')}", reply_markup=keyboard)
        except:
            pass 
        
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

        formatted_lessons =[]
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
        active_subs =[s for s in subs if s['is_active']]
        
        kb = await get_myschedule_filters_keyboard(filters, active_subs, user_id)
        await callback.message.edit_text("⚙️ Настройка отображения:", reply_markup=kb)
        await callback.answer()

    async def handle_myschedule_toggle_filter(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        filters = await self._get_user_filters(user_id)
        data_parts = callback.data.split(":")
        action_type = data_parts[0] 
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
        
        subs, _ = await database.get_user_subscriptions(user_id, page=0, page_size=100)
        active_subs = [s for s in subs if s['is_active']]
        kb = await get_myschedule_filters_keyboard(filters, active_subs, user_id)
        
        try:
            await callback.message.edit_reply_markup(reply_markup=kb)
        except: pass
        await callback.answer()

    async def handle_myschedule_back_to_cal(self, callback: CallbackQuery):
        user_id = callback.from_user.id
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
        
        formatted_lessons =[]
        for l in schedule:
            l_copy = l.copy()
            l_copy['lecturer_title'] = f"{l_copy.get('lecturer_title','')} ({l.get('source_entity')})"
            formatted_lessons.append(l_copy)
            
        header = f"Сводка: {start_date.strftime('%d.%m')} - {end_date.strftime('%d.%m')}"
        
        text = await format_schedule(formatted_lessons, lang, header, "mixed", user_id, start_date, is_week_view=True)
        
        if len(text) > 4000:
            text = text[:4000] + "\n\n...(сообщение обрезано, слишком много пар)..."

        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="📲 Экспорт iCal (Неделя)", callback_data=f"mysch_ical:{start_date_str}:7"))
        builder.row(InlineKeyboardButton(text="⬅️ Назад к календарю", callback_data="mysch_back_cal"))
        
        try:
            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception as e:
            await callback.message.answer_document(
                BufferedInputFile(text.encode('utf-8'), filename="schedule.txt"),
                caption="Текст расписания слишком длинный для одного сообщения.",
                reply_markup=builder.as_markup()
            )
        await callback.answer()

    async def handle_myschedule_export_ical(self, callback: CallbackQuery):
        try:
            _, start_date_str, days_count_str = callback.data.split(":")
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            days_count = int(days_count_str)
            end_date = start_date + timedelta(days=days_count - 1) 
        except ValueError:
            await callback.answer("Ошибка данных.", show_alert=True)
            return

        user_id = callback.from_user.id
        lang = await translator.get_language(user_id)
        
        await callback.answer("Генерация файла...")
        
        subs, _ = await database.get_user_subscriptions(user_id, page=0, page_size=100)
        active_subs =[s for s in subs if s['is_active']]
        filters = await self._get_user_filters(user_id)
        
        schedule = await get_aggregated_schedule(user_id, active_subs, start_date, end_date, filters)
        
        if not schedule:
            await callback.message.answer("Нет занятий для экспорта.")
            return

        ical_data = generate_ical_from_aggregated_schedule(schedule)
        
        filename = f"myschedule_{start_date_str}_{days_count}days.ics"
        caption = translator.gettext(lang, "schedule_export_ical_caption", start=start_date.strftime('%d.%m'), end=end_date.strftime('%d.%m'))
        
        await callback.message.answer_document(
            document=BufferedInputFile(ical_data, filename=filename),
            caption=caption
        )
        
    async def _resolve_entity_name(self, user_id: int, entity_type: str, entity_id: str, schedule_data: list = None) -> str:
        cached_search = await redis_client.get_user_cache(user_id, 'schedule_search')
        if cached_search and cached_search.get('results'):
            item = next((i for i in cached_search['results'] if str(i['id']) == str(entity_id)), None)
            if item: return item['label']

        history_key = f"schedule_history:{user_id}"
        history_raw = await redis_client.client.lrange(history_key, 0, -1)
        for item_json in history_raw:
            try:
                item = json.loads(item_json)
                if str(item.get('entity_id')) == str(entity_id) and item.get('entity_type') == entity_type:
                    return item['entity_name']
            except: continue

        subs, _ = await database.get_user_subscriptions(user_id, page=0, page_size=100)
        sub = next((s for s in subs if str(s['entity_id']) == str(entity_id) and s['entity_type'] == entity_type), None)
        if sub: return sub['entity_name']

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
        secret = await database.get_or_create_calendar_secret(user_id)
        
        from bot.config import PUBLIC_API_URL
        base_url = PUBLIC_API_URL.rstrip('/')
        http_link = f"{base_url}/api/cal/{secret}.ics"
        
        text = (
            "🔗 <b>Ваша персональная ссылка на расписание</b>\n\n"
            f"<code>{http_link}</code>\n\n"
            "<b>Как добавить, чтобы оно обновлялось само:</b>\n"
            "• <b>iOS (iPhone/Mac):</b> Нажмите кнопку ниже. Если не сработает, то Настройки -> Календарь -> Учетные записи -> Добавить -> Другое -> Календарь по подписке.\n"
            "• <b>Google Calendar:</b> Откройте <u>веб-версию (на ПК)</u>, нажмите «+» рядом с «Другие календари» -> «Добавить по URL» и вставьте ссылку выше.\n\n"
            "<i>Расписание выгружается на 3 месяца вперед и обновляется автоматически.</i>"
        )

        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="📱 Добавить на iOS / Mac", url=http_link))
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
# bot/handlers/schedule.py

from aiogram import F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta, time, date
import logging
import re
import hashlib

from shared_lib.services.university_api import RuzAPIClient # Import the class for type hinting
from shared_lib.services.schedule_service import format_schedule, generate_ical_from_schedule
from bot.keyboards import get_schedule_type_keyboard, build_search_results_keyboard, code_path_cache, build_calendar_keyboard, InlineKeyboardButton
from shared_lib.i18n import translator
from bot import database
from shared_lib.redis_client import redis_client
import asyncio


router = Router()

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

    async def cmd_schedule(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        lang = await translator.get_user_language(user_id)
        await message.answer(
            translator.gettext(lang, "schedule_welcome"),
            reply_markup=await get_schedule_type_keyboard(lang)
        )

    async def handle_schedule_type(self, callback: CallbackQuery, state: FSMContext):
        search_type = callback.data.split("_")[-1]
        await state.set_state(ScheduleStates.awaiting_search_query)
        await state.update_data(search_type=search_type)
        
        user_id = callback.from_user.id
        lang = await translator.get_user_language(user_id)
        
        prompt_key = f"schedule_prompt_for_query_{search_type}"
        await callback.message.edit_text(translator.gettext(lang, prompt_key))
        await callback.answer()

    async def _perform_search_and_reply(self, message: Message, status_msg: Message, query: str, search_type: str):
        """Helper function to run the search in the background and send results."""
        user_id = message.from_user.id
        lang = await translator.get_user_language(user_id)
        
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
        lang = await translator.get_user_language(user_id)
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
        lang = await translator.get_user_language(user_id)
        await callback.message.edit_text(translator.gettext(lang, "schedule_loading"))

        try:
            today = datetime.now()
            api_date_str = today.strftime("%Y.%m.%d")
            schedule_data = await self.api_client.get_schedule(entity_type, entity_id, start=api_date_str, finish=api_date_str)
            entity_name = schedule_data[0].get(entity_type, "Unknown") if schedule_data else "Unknown"
            formatted_text = format_schedule(schedule_data, lang, entity_name, entity_type, start_date=today.date())

            await callback.message.edit_text(formatted_text, parse_mode="HTML")
            await self._send_actions_menu(callback.message, lang, entity_type, entity_id, entity_name, view_type='daily_initial')
        except Exception as e:
            logging.error(f"Failed to get today's schedule for {entity_type}:{entity_id}. Error: {e}", exc_info=True)
            await callback.message.edit_text(translator.gettext(lang, "schedule_api_error"))

    async def handle_open_calendar(self, callback: CallbackQuery):
        await callback.answer()
        _, entity_type, entity_id = callback.data.split(":")
        lang = await translator.get_user_language(callback.from_user.id)
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
                    await callback.answer(translator.gettext(await translator.get_user_language(callback.from_user.id), "calendar_already_on_today"), show_alert=False)
                    return
                year, month = now.year, now.month

            lang = await translator.get_user_language(callback.from_user.id)
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
        lang = await translator.get_user_language(user_id)
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
            lang = await translator.get_user_language(callback.from_user.id)
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

        # Context-specific buttons
        if view_type == 'daily_initial': # After initial search result
            open_calendar_callback = f"sch_open_calendar:{entity_type}:{entity_id}"
            builder.row(InlineKeyboardButton(text=translator.gettext(lang, "schedule_view_calendar"), callback_data=open_calendar_callback))
        elif view_type == 'daily_from_calendar' and date_info: # After picking a date from calendar
            back_to_cal_callback = f"cal_back:{date_info['year']}:{date_info['month']}:{entity_type}:{entity_id}:{date_info['date_str']}"
            builder.row(InlineKeyboardButton(text=translator.gettext(lang, "schedule_back_to_calendar"), callback_data=back_to_cal_callback))
        elif view_type == 'weekly' and date_info: # After picking a week
            ical_callback = f"sch_export_ical:{entity_type}:{entity_id}:{date_info['date_str']}"
            builder.row(InlineKeyboardButton(text=translator.gettext(lang, "schedule_export_ical"), callback_data=ical_callback))
            # Also add a button to go back to the calendar view for that month
            back_to_cal_callback = f"cal_back:{date_info['year']}:{date_info['month']}:{entity_type}:{entity_id}:{date_info['date_str']}"
            builder.row(InlineKeyboardButton(text=translator.gettext(lang, "schedule_back_to_calendar"), callback_data=back_to_cal_callback))

        # Back to search results (always relevant)
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "schedule_back_to_results"), callback_data="sch_back_to_results"))
        return builder

    async def handle_date_selection(self, callback: CallbackQuery):
        await callback.answer()
        _, entity_type, entity_id, date_str = callback.data.split(":")
        user_id = callback.from_user.id
        lang = await translator.get_user_language(user_id)
        await callback.message.edit_text(translator.gettext(lang, "schedule_loading"))
        try:
            # --- FIX for BUTTON_DATA_INVALID ---
            # If the ID is a hash, get the real ID from cache for the API call.
            original_entity_id = entity_id
            if len(entity_id) == 16 and not entity_id.isdigit():
                original_entity_id = code_path_cache.get(entity_id, entity_id)

            selected_date = datetime.strptime(date_str, "%Y-%m-%d")
            api_date_str = selected_date.strftime("%Y.%m.%d")
            schedule_data = await self.api_client.get_schedule(entity_type, original_entity_id, start=api_date_str, finish=api_date_str)
            entity_name = schedule_data[0].get(entity_type, "Unknown") if schedule_data else "Unknown"
            formatted_text = format_schedule(schedule_data, lang, entity_name, entity_type, start_date=selected_date.date())
            
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
        lang = await translator.get_user_language(user_id)
        await callback.message.edit_text(translator.gettext(lang, "schedule_loading"))
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()

            # --- FIX for BUTTON_DATA_INVALID ---
            original_entity_id = entity_id
            if len(entity_id) == 16 and not entity_id.isdigit():
                original_entity_id = code_path_cache.get(entity_id, entity_id)

            end_date = start_date + timedelta(days=6)
            api_start_str, api_end_str = start_date.strftime("%Y.%m.%d"), end_date.strftime("%Y.%m.%d")

            schedule_data = await self.api_client.get_schedule(entity_type, original_entity_id, start=api_start_str, finish=api_end_str)
            entity_name = schedule_data[0].get(entity_type, "Unknown") if schedule_data else "Unknown"
            formatted_text = format_schedule(schedule_data, lang, entity_name, entity_type, start_date=start_date, is_week_view=True)
            
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
        api_start_str, api_end_str = start_date.strftime("%Y.%m.%d"), end_date.strftime("%Y.%m.%d")
        
        # --- FIX for BUTTON_DATA_INVALID ---
        original_entity_id = entity_id
        if len(entity_id) == 16 and not entity_id.isdigit():
            original_entity_id = code_path_cache.get(entity_id, entity_id)

        schedule_data = await self.api_client.get_schedule(entity_type, original_entity_id, start=api_start_str, finish=api_end_str)
        
        if schedule_data:
            entity_name = schedule_data[0].get(entity_type)
        else:
            # If no schedule, get name from search cache as a fallback
            cached_search = await redis_client.get_user_cache(user_id, 'schedule_search')
            # Find the specific entity name from the cached search results
            entity_name = next((item['label'] for item in cached_search.get('results', []) if str(item['id']) == original_entity_id), 'Unknown') if cached_search else 'Unknown'
        
        ical_string = generate_ical_from_schedule(schedule_data, entity_name)
        file_bytes = ical_string.encode('utf-8')
        filename = f"schedule_{entity_name.replace(' ', '_')}_{start_date_str}.ics"
        
        return file_bytes, filename, start_date, end_date

    async def handle_ical_export(self, callback: CallbackQuery):
        await callback.answer()
        _, entity_type, entity_id, start_date_str = callback.data.split(":")
        user_id = callback.from_user.id
        lang = await translator.get_user_language(user_id)
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
        lang = await translator.get_user_language(user_id)
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
        lang = await translator.get_user_language(user_id)
        time_str = message.text.strip()
        if not re.match(r"^\d{2}:\d{2}$", time_str):
            await message.reply(translator.gettext(lang, "schedule_invalid_time_format"))
            return
        try:
            notification_time = time.fromisoformat(time_str)
            sub_data = await state.get_data()
            await database.add_schedule_subscription(user_id, sub_data['sub_entity_type'], sub_data['sub_entity_id'], sub_data['sub_entity_name'], notification_time)
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
        today_str = today_dt.strftime("%Y.%m.%d")
        try:
            schedule_data = await self.api_client.get_schedule(sub['entity_type'], sub['entity_id'], start=today_str, finish=today_str)
            formatted_text = format_schedule(schedule_data, lang, sub['entity_name'], sub['entity_type'], start_date=today_dt.date())
            await message.answer(formatted_text, parse_mode="HTML")
        except TelegramForbiddenError:
            logging.warning(f"Bot is blocked by user {user_id}. Cannot send schedule.")
            raise  # Re-raise to stop sending to this user
        except Exception as e:
            logging.error(f"Failed to send schedule to user {user_id} for entity {sub['entity_name']}: {e}", exc_info=True)

    async def cmd_my_schedule(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        lang = await translator.get_user_language(user_id)
        subscriptions, _ = await database.get_user_subscriptions(user_id, page=0, page_size=100)
        if not subscriptions:
            await message.answer(translator.gettext(lang, "myschedule_no_subscriptions"))
            return
        status_msg = await message.answer(translator.gettext(lang, "myschedule_loading"))
        today_dt = datetime.now()

        for sub in subscriptions:
            try:
                await self._send_single_schedule_update(message, lang, sub, today_dt)
                await asyncio.sleep(0.2)  # Small delay to avoid hitting rate limits
            except TelegramForbiddenError:
                break  # Stop trying to send messages to this user

        await status_msg.delete()
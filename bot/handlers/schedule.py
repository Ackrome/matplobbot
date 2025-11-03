# bot/handlers/schedule.py

from aiogram import F, Router
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta, time, date
import logging
import re

from shared_lib.services.university_api import RuzAPIClient # Import the class for type hinting
from shared_lib.services.schedule_service import format_schedule
from bot.keyboards import get_schedule_type_keyboard, build_search_results_keyboard, code_path_cache
from shared_lib.i18n import translator
from bot import database
import asyncio


router = Router()

class ScheduleStates(StatesGroup):
    awaiting_search_query = State()
    awaiting_subscription_time = State()

@router.message(Command("schedule"))
async def cmd_schedule(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await translator.get_user_language(user_id)
    await message.answer(
        translator.gettext(lang, "schedule_welcome"),
        reply_markup=await get_schedule_type_keyboard(lang)
    )

@router.callback_query(F.data.startswith("sch_type_"))
async def handle_schedule_type(callback: CallbackQuery, state: FSMContext):
    search_type = callback.data.split("_")[-1]
    await state.set_state(ScheduleStates.awaiting_search_query)
    await state.update_data(search_type=search_type)
    
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    
    prompt_key = f"schedule_prompt_for_query_{search_type}"
    await callback.message.edit_text(translator.gettext(lang, prompt_key))
    await callback.answer()

@router.message(ScheduleStates.awaiting_search_query)
async def handle_search_query(message: Message, state: FSMContext, ruz_api_client: RuzAPIClient):
    user_id = message.from_user.id
    lang = await translator.get_user_language(user_id)
    data = await state.get_data()
    search_type = data['search_type']
    
    status_msg = await message.answer(translator.gettext(lang, "search_in_progress", query=message.text))
    
    try:
        results = await ruz_api_client.search(term=message.text, search_type=search_type)
        if not results:
            await status_msg.edit_text(translator.gettext(lang, "schedule_no_results", query=message.text))
            return

        keyboard = build_search_results_keyboard(results, search_type)
        await status_msg.edit_text(
            translator.gettext(lang, "schedule_results_found", count=len(results)),
            reply_markup=keyboard
        )

    except Exception as e:
        logging.error(f"Failed to query RUZ API. Error: {e}", exc_info=True)
        await status_msg.edit_text(translator.gettext(lang, "schedule_api_error"))
        # Here you would add logging or Sentry capture
    finally:
        await state.clear()

@router.callback_query(F.data.startswith("sch_result_"))
async def handle_result_selection(callback: CallbackQuery, state: FSMContext, ruz_api_client: RuzAPIClient):
    # Acknowledge the callback immediately to prevent "query is too old" error
    await callback.answer()

    _, entity_type, entity_id = callback.data.split(":")
    
    # For now, just fetch today's schedule. Can add date selection later.
    today_dt = datetime.now()
    today_str = today_dt.strftime("%Y.%m.%d")
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    await callback.message.edit_text(translator.gettext(lang, "schedule_loading"))

    try:
        schedule_data = await ruz_api_client.get_schedule(entity_type, entity_id, start=today_str, finish=today_str)
        entity_name = schedule_data[0].get(entity_type, "Unknown") if schedule_data else "Unknown"

        formatted_text = format_schedule(schedule_data, lang, entity_name, start_date=today_dt.date())

        # Create the subscribe button with the new, specific callback data format
        subscribe_kb = build_search_results_keyboard(
            [{'label': translator.gettext(lang, "schedule_subscribe_button"), 'id': f"{entity_type}:{entity_id}:{entity_name}"}],
            'subscribe'
        )

        await callback.message.edit_text(
            formatted_text, 
            parse_mode="Markdown", 
            reply_markup=subscribe_kb
        )
    except Exception as e:
        logging.error(f"Failed to get schedule for {entity_type}:{entity_id}. Error: {e}", exc_info=True)
        lang = await translator.get_user_language(user_id)
        await callback.message.edit_text(translator.gettext(lang, "schedule_api_error"))

@router.callback_query(F.data.startswith("sch_subscribe_hash:"))
async def handle_subscribe_button(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    
    try:
        # Retrieve the full data from the cache using the hash
        data_hash = callback.data.split(":", 1)[1]
        data_part = code_path_cache.get(data_hash)
        entity_type, entity_id, entity_name = data_part.split(":", 2)
    except ValueError:
        logging.error(f"Invalid subscribe callback data: {callback.data}")
        await callback.answer(translator.gettext(lang, "schedule_subscribe_error"), show_alert=True)
        return

    await state.set_state(ScheduleStates.awaiting_subscription_time)
    await state.update_data(
        sub_entity_type=entity_type,
        sub_entity_id=entity_id,
        sub_entity_name=entity_name
    )

    await callback.message.edit_text(translator.gettext(lang, "schedule_prompt_for_time"))
    await callback.answer()

@router.message(ScheduleStates.awaiting_subscription_time)
async def handle_subscription_time(message: Message, state: FSMContext):
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

@router.message(Command("myschedule"))
async def cmd_my_schedule(message: Message, state: FSMContext, ruz_api_client: RuzAPIClient):
    """Sends the user all their subscribed schedules for the current day."""
    user_id = message.from_user.id
    lang = await translator.get_user_language(user_id)
    
    # Fetch all subscriptions, not paginated
    subscriptions, total_count = await database.get_user_subscriptions(user_id, page=0, page_size=100)

    if not subscriptions:
        await message.answer(translator.gettext(lang, "myschedule_no_subscriptions"))
        return

    status_msg = await message.answer(translator.gettext(lang, "myschedule_loading"))

    today_dt = datetime.now()
    today_str = today_dt.strftime("%Y.%m.%d")

    for sub in subscriptions:
        try:
            schedule_data = await ruz_api_client.get_schedule(
                sub['entity_type'], sub['entity_id'], start=today_str, finish=today_str
            )
            formatted_text = format_schedule(schedule_data, lang, sub['entity_name'], start_date=today_dt.date())
            await message.answer(formatted_text, parse_mode="Markdown")
        except TelegramForbiddenError:
            logging.warning(f"Bot is blocked by user {user_id}. Cannot send schedule.")
            # Optionally, deactivate this user's subscriptions here
            break # Stop trying to send messages to this user
        except Exception as e:
            logging.error(f"Failed to send schedule to user {user_id} for entity {sub['entity_name']}: {e}", exc_info=True)
        await asyncio.sleep(0.2) # Small delay to avoid hitting rate limits
    
    await status_msg.delete()
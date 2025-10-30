# bot/handlers/schedule.py

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta, time
import logging
import re

from bot.services.university_api import RuzAPIClient # Import the class for type hinting
from bot.services.schedule_service import format_schedule
from bot.keyboards import get_schedule_type_keyboard, build_search_results_keyboard
from bot.i18n import translator
from bot import database


router = Router()

class ScheduleStates(StatesGroup):
    awaiting_search_query = State()
    awaiting_subscription_time = State()

@router.message(F.text == "/schedule")
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
    today = datetime.now().strftime("%Y.%m.%d")
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    await callback.message.edit_text(translator.gettext(lang, "schedule_loading"))

    try:
        schedule_data = await ruz_api_client.get_schedule(entity_type, entity_id, start=today, finish=today)
        entity_name = schedule_data[0].get(entity_type, "Unknown") if schedule_data else "Unknown"

        formatted_text = format_schedule(schedule_data, lang, entity_name)

        builder = InlineKeyboardBuilder()
        subscribe_button = build_search_results_keyboard(
            [{'label': translator.gettext(lang, "schedule_subscribe_button"), 'id': f"{entity_type}:{entity_id}:{entity_name}", 'type': 'subscribe'}],
            'subscribe'
        )
        builder.row(*subscribe_button.inline_keyboard[0])

        await callback.message.edit_text(
            formatted_text, 
            parse_mode="Markdown", 
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logging.error(f"Failed to get schedule for {entity_type}:{entity_id}. Error: {e}", exc_info=True)
        lang = await translator.get_user_language(user_id)
        await callback.message.edit_text(translator.gettext(lang, "schedule_api_error"))

@router.callback_query(F.data.startswith("sch_result_:subscribe:"))
async def handle_subscribe_button(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    
    try:
        _, _, data_part = callback.data.split(":", 2)
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
# bot/handlers/schedule.py

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from datetime import datetime, timedelta
import logging

from bot.services.university_api import ruz_api_client
from bot.services.schedule_service import format_schedule
from bot.keyboards import get_schedule_type_keyboard, build_search_results_keyboard
from bot.i18n import translator


router = Router()

class ScheduleStates(StatesGroup):
    awaiting_search_query = State()
    choosing_date = State()

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
async def handle_search_query(message: Message, state: FSMContext):
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
async def handle_result_selection(callback: CallbackQuery):
    _, entity_type, entity_id = callback.data.split(":")
    
    # For now, just fetch today's schedule. Can add date selection later.
    today = datetime.now().strftime("%Y.%m.%d")
    
    await callback.message.edit_text("Загружаю расписание...")
    
    try:
        schedule_data = await ruz_api_client.get_schedule(entity_type, entity_id, start=today, finish=today)
        
        user_id = callback.from_user.id
        lang = await translator.get_user_language(user_id)
        
        formatted_text = format_schedule(schedule_data, lang)
        await callback.message.edit_text(
            formatted_text, 
            parse_mode="Markdown", 
            reply_markup=None # Add back button later
        )
    except Exception as e:
        await callback.message.edit_text("Произошла ошибка при загрузке расписания.")
        # Add logging
    
    await callback.answer()
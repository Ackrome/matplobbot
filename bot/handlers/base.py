# bot/handlers/base.py
import logging
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove, InlineKeyboardButton
from aiogram.filters import CommandStart, Command, StateFilter, Filter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .. import keyboards as kb, database
from . import library, github, rendering, settings # Импортируем для колбэков помощи
from ..i18n import translator

router = Router()

class Onboarding(Filter):
    async def __call__(self, message: Message) -> bool:
        return not await database.is_onboarding_completed(message.from_user.id)

@router.message(CommandStart(), Onboarding())
async def command_start_onboarding(message: Message, state: FSMContext):
    """Handles the very first /start command from a new user."""
    user_id = message.from_user.id
    lang = await translator.get_user_language(user_id)
    await state.set_state("onboarding:step1")

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_next"), callback_data="onboarding_next"))

    await message.answer(
        translator.gettext(lang, "start_onboarding_1"),
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "onboarding_next", StateFilter("onboarding:step1"))
async def onboarding_step2(callback: CallbackQuery, state: FSMContext):
    lang = await translator.get_user_language(callback.from_user.id)
    await state.set_state("onboarding:step2")
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_add_repo"), callback_data="manage_repos"))
    await callback.message.edit_text(
        translator.gettext(lang, "start_onboarding_2"),
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "onboarding_next", StateFilter("onboarding:step3"))
async def onboarding_step4(callback: CallbackQuery, state: FSMContext):
    lang = await translator.get_user_language(callback.from_user.id)
    await state.set_state("onboarding:step4")
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_try_latex"), callback_data="help_cmd_latex"))
    await callback.message.edit_text(
        translator.gettext(lang, "start_onboarding_4"),
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "onboarding_next", StateFilter("onboarding:step5"))
async def onboarding_finish(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    await state.clear()
    await database.set_onboarding_completed(user_id)
    await callback.message.edit_text(translator.gettext(lang, "start_onboarding_5"))
    await callback.message.answer(
        translator.gettext(lang, "choose_next_command"),
        reply_markup=await kb.get_main_reply_keyboard(user_id)
    )
    await callback.answer()

@router.message(CommandStart())
async def command_start_regular(message: Message):
    lang = await translator.get_user_language(message.from_user.id)
    await message.answer(
        translator.gettext(lang, "start_welcome", full_name=message.from_user.full_name),
        reply_markup=await kb.get_main_reply_keyboard(message.from_user.id)
    )
    
@router.message(Command('help'))
async def comand_help(message: Message):
    lang = await translator.get_user_language(message.from_user.id)
    await message.answer(
        translator.gettext(lang, "help_menu_header"),
        reply_markup=await kb.get_help_inline_keyboard(message.from_user.id)
    )

@router.message(StateFilter('*'), Command("cancel"))
@router.message(StateFilter('*'), F.text.casefold() == "отмена")
async def cancel_handler(message: Message, state: FSMContext) -> None:
    """
    Позволяет пользователю отменить любое действие (выйти из любого состояния).
    """
    user_id = message.from_user.id
    lang = await translator.get_user_language(user_id)
    current_state = await state.get_state()
    if current_state is None:
        await message.answer(
            translator.gettext(lang, "cancel_no_active_command"),
            reply_markup=await kb.get_main_reply_keyboard(user_id)
        )
        return

    logging.info(f"Cancelling state {current_state} for user {user_id}")
    await state.clear()
    # Убираем клавиатуру предыдущего шага и ставим основную
    await message.answer(
        translator.gettext(lang, "cancel_action_cancelled"),
        reply_markup=await kb.get_main_reply_keyboard(user_id),
    )


##################################################################################################
# HELP COMMAND CALLBACKS
##################################################################################################

@router.callback_query(F.data == "help_cmd_matp_all")
async def cq_help_cmd_matp_all(callback: CallbackQuery):
    """Handler for '/matp_all' button from help menu."""
    await callback.answer()
    # Повторяем логику команды /matp_all
    await library.matp_all_command_inline(callback.message)

@router.callback_query(F.data == "help_cmd_matp_search")
async def cq_help_cmd_matp_search(callback: CallbackQuery, state: FSMContext):
    """Handler for '/matp_search' button from help menu."""
    await callback.answer()
    # Повторяем логику команды /matp_search
    await state.set_state(library.Search.query)
    await callback.message.answer("Введите ключевые слова для поиска по примерам кода:", reply_markup=ReplyKeyboardRemove())

@router.callback_query(F.data == "help_cmd_lec_search")
async def cq_help_cmd_lec_search(callback: CallbackQuery, state: FSMContext):
    """Handler for '/lec_search' button from help menu."""
    await callback.answer()
    # Повторяем логику команды /lec_search
    await state.set_state(library.MarkdownSearch.query)
    await callback.message.answer("Введите ключевые слова для поиска по конспектам:", reply_markup=ReplyKeyboardRemove())

@router.callback_query(F.data == "help_cmd_lec_all")
async def cq_help_cmd_lec_all(callback: CallbackQuery):
    """Handler for '/lec_all' button from help menu."""
    await callback.answer()
    await github.lec_all_command(callback.message)

@router.callback_query(F.data == "help_cmd_favorites")
async def cq_help_cmd_favorites(callback: CallbackQuery):
    """Handler for '/favorites' button from help menu."""
    await callback.answer()
    # Повторяем логику команды /favorites
    # favorites_command ожидает объект Message, callback.message подходит
    await library.favorites_command(callback.message)

@router.callback_query(F.data == "help_cmd_latex")
async def cq_help_cmd_latex(callback: CallbackQuery, state: FSMContext):
    """Handler for '/latex' button from help menu."""
    await callback.answer()
    # Повторяем логику команды /latex
    await rendering.latex_command(callback.message, state)

@router.callback_query(F.data == "help_cmd_mermaid")
async def cq_help_cmd_mermaid(callback: CallbackQuery, state: FSMContext):
    """Handler for '/mermaid' button from help menu."""
    await callback.answer()
    # Повторяем логику команды /mermaid
    await rendering.mermaid_command(callback.message, state)

@router.callback_query(F.data == "help_cmd_settings")
async def cq_help_cmd_settings(callback: CallbackQuery):
    """Handler for '/settings' button from help menu."""
    await callback.answer()
    # Повторяем логику команды /settings
    keyboard = await settings.get_settings_keyboard(callback.from_user.id)
    await callback.message.answer(
        "⚙️ Настройки:",
        reply_markup=keyboard.as_markup()
    )




@router.callback_query(F.data == "help_cmd_help")
async def cq_help_cmd_help(callback: CallbackQuery):
    """Handler for '/help' button from help menu. Edits the message."""
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    try:
        # Пытаемся отредактировать сообщение, чтобы обновить его до актуального состояния
        await callback.message.edit_text(
            translator.gettext(lang, "help_menu_header"),
            reply_markup=await kb.get_help_inline_keyboard(user_id)
        )
        await callback.answer()
    except TelegramBadRequest as e:
        if "message is not modified" in e.message:
            await callback.answer(translator.gettext(lang, "help_already_in_menu"))
        else:
            raise
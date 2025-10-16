# bot/handlers/base.py
import logging
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext

from .. import keyboards as kb
from . import library, github, rendering, settings # Импортируем для колбэков помощи

router = Router()

@router.message(CommandStart())
async def comand_start(message: Message):
    await message.answer(
        f'Привет, {message.from_user.full_name}!',
        reply_markup=kb.get_main_reply_keyboard(message.from_user.id)
    )
    
@router.message(Command('help'))
async def comand_help(message: Message):
    await message.answer(
        'Это бот для поиска примеров кода по библиотеке matplobblib.\n\n'
        'Нажмите на кнопку, чтобы выполнить команду:',
        reply_markup=kb.get_help_inline_keyboard(message.from_user.id)
    )

@router.message(StateFilter('*'), Command("cancel"))
@router.message(StateFilter('*'), F.text.casefold() == "отмена")
async def cancel_handler(message: Message, state: FSMContext) -> None:
    """
    Позволяет пользователю отменить любое действие (выйти из любого состояния).
    """
    current_state = await state.get_state()
    if current_state is None:
        await message.answer(
            "Нет активной команды для отмены.",
            reply_markup=kb.get_main_reply_keyboard(message.from_user.id)
        )
        return

    logging.info(f"Cancelling state {current_state} for user {message.from_user.id}")
    await state.clear()
    # Убираем клавиатуру предыдущего шага и ставим основную
    await message.answer(
        "Действие отменено.",
        reply_markup=kb.get_main_reply_keyboard(message.from_user.id),
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
    try:
        # Пытаемся отредактировать сообщение, чтобы обновить его до актуального состояния
        await callback.message.edit_text(
            'Это бот для поиска примеров кода по библиотеке matplobblib.\n\n'
            'Нажмите на кнопку, чтобы выполнить команду:',
            reply_markup=kb.get_help_inline_keyboard(callback.from_user.id)
        )
        await callback.answer()
    except TelegramBadRequest as e:
        # Если сообщение не изменилось, Telegram выдаст ошибку.
        # Мы просто отвечаем на колбэк, чтобы убрать "часики" с кнопки.
        if "message is not modified" in e.message:
            await callback.answer("Вы уже в меню помощи.")
        else:
            # Перевыбрасываем другие, непредвиденные ошибки
            raise
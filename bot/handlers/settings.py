import logging

from aiogram import F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.filters import  Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from shared_lib.database import get_user_settings, update_user_settings_db, get_user_repos
from shared_lib.i18n import translator


router = Router()

AVAILABLE_LANGUAGES = {"en": "English", "ru": "Русский"}
LANGUAGE_CODES = list(AVAILABLE_LANGUAGES.keys())

##################################################################################################
# SETTINGS
##################################################################################################

# Теперь эта функция асинхронная, так как обращается к БД
async def get_settings_keyboard(user_id: int) -> InlineKeyboardBuilder:
    """Создает инлайн-клавиатуру для настроек пользователя."""
    settings = await get_user_settings(user_id)
    lang = settings.get('language', 'en')
    builder = InlineKeyboardBuilder()

    docstring_status_key = "settings_docstring_on" if settings['show_docstring'] else "settings_docstring_off"
    show_docstring_status = translator.gettext(lang, docstring_status_key)

    builder.row(
        InlineKeyboardButton(
            text=translator.gettext(lang, "settings_show_docstring", status=show_docstring_status),
            callback_data="settings_toggle_docstring"
        )
    )

    # Настройка отображения Markdown
    md_mode = settings.get('md_display_mode', 'md_file')
    md_mode_map = {
        'md_file': translator.gettext(lang, 'settings_md_mode_md'),
        'html_file': translator.gettext(lang, 'settings_md_mode_html'),
        'pdf_file': translator.gettext(lang, 'settings_md_mode_pdf')
    }
    md_mode_text = md_mode_map.get(md_mode, translator.gettext(lang, 'settings_md_mode_unknown'))

    builder.row(InlineKeyboardButton(
        text=translator.gettext(lang, "settings_md_display_mode", mode_text=md_mode_text),
        callback_data="settings_cycle_md_mode"
    ))

    # Настройка отступов LaTeX
    padding = settings['latex_padding']
    builder.row(
        InlineKeyboardButton(text="➖", callback_data="latex_padding_decr"),
        InlineKeyboardButton(text=translator.gettext(lang, "settings_latex_padding", padding=padding), callback_data="noop"),
        InlineKeyboardButton(text="➕", callback_data="latex_padding_incr")
    )

    builder.row(
        InlineKeyboardButton(text="➖", callback_data="latex_dpi_decr"),
        InlineKeyboardButton(text=translator.gettext(lang, "settings_latex_dpi", dpi=settings['latex_dpi']), callback_data="noop"),
        InlineKeyboardButton(text="➕", callback_data="latex_dpi_incr")
    )

    # --- Управление репозиториями ---
    user_repos = await get_user_repos(user_id)
    repo_button_key = "settings_manage_repos_btn" if user_repos else "settings_add_repos_btn"
    repo_button_text = translator.gettext(lang, repo_button_key)
    builder.row(InlineKeyboardButton(
        text=repo_button_text,
        callback_data="manage_repos"
    ))

    # --- Language Setting ---
    current_lang_name = AVAILABLE_LANGUAGES.get(lang, "Unknown")
    builder.row(InlineKeyboardButton(
        text=translator.gettext(lang, "settings_language_btn", lang_name=current_lang_name),
        callback_data="settings_cycle_language"
    ))

    return builder

@router.message(Command('settings'))
async def command_settings(message: Message):
    """Обработчик команды /settings."""
    user_id = message.from_user.id
    lang = await translator.get_user_language(user_id)
    keyboard = await get_settings_keyboard(user_id)
    await message.answer(
        translator.gettext(lang, "settings_menu_header"),
        reply_markup=keyboard.as_markup()
    )

@router.callback_query(F.data == "settings_toggle_docstring")
async def cq_toggle_docstring(callback: CallbackQuery):
    """Обработчик для переключения настройки 'show_docstring'."""
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    settings = await get_user_settings(user_id)
    settings['show_docstring'] = not settings['show_docstring']
    await update_user_settings_db(user_id, settings) # Сохраняем обновленные настройки в БД
    keyboard = await get_settings_keyboard(user_id)
    await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
    await callback.answer(translator.gettext(lang, "settings_docstring_updated"))

MD_DISPLAY_MODES = ['md_file', 'html_file', 'pdf_file']

@router.callback_query(F.data == "settings_cycle_md_mode")
async def cq_cycle_md_mode(callback: CallbackQuery):
    """Обработчик для переключения режима отображения Markdown."""
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    settings = await get_user_settings(user_id)

    current_mode = settings.get('md_display_mode', 'md_file')
    try:
        current_index = MD_DISPLAY_MODES.index(current_mode)
        next_index = (current_index + 1) % len(MD_DISPLAY_MODES)
        new_mode = MD_DISPLAY_MODES[next_index]
    except ValueError:
        # Если текущий режим некорректен, сбрасываем на дефолтный
        new_mode = MD_DISPLAY_MODES[0]

    settings['md_display_mode'] = new_mode
    await update_user_settings_db(user_id, settings)

    keyboard = await get_settings_keyboard(user_id)
    await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())

    md_mode_map = {
        'md_file': translator.gettext(lang, 'settings_md_mode_md'),
        'html_file': translator.gettext(lang, 'settings_md_mode_html'),
        'pdf_file': translator.gettext(lang, 'settings_md_mode_pdf')
    }
    await callback.answer(translator.gettext(lang, "settings_md_mode_updated", mode_text=md_mode_map[new_mode]))
    
@router.callback_query(F.data == "settings_cycle_language")
async def cq_cycle_language(callback: CallbackQuery):
    """Cycles through available languages."""
    user_id = callback.from_user.id
    settings = await get_user_settings(user_id)
    current_lang = settings.get('language', 'en')

    try:
        current_index = LANGUAGE_CODES.index(current_lang)
        next_index = (current_index + 1) % len(LANGUAGE_CODES)
        new_lang = LANGUAGE_CODES[next_index]
    except ValueError:
        new_lang = LANGUAGE_CODES[0]

    settings['language'] = new_lang
    await update_user_settings_db(user_id, settings)

    keyboard = await get_settings_keyboard(user_id)
    await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
    await callback.answer(translator.gettext(new_lang, "settings_language_updated", lang_name=AVAILABLE_LANGUAGES[new_lang]))

@router.callback_query(F.data == "back_to_settings")
async def cq_back_to_settings(callback: CallbackQuery):
    """Returns to the main settings menu."""
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    keyboard = await get_settings_keyboard(user_id)
    await callback.message.edit_text(translator.gettext(lang, "settings_menu_header"), reply_markup=keyboard.as_markup())
    await callback.answer()
    
##################################################################################################
# LATEX SETTINGS
##################################################################################################

@router.callback_query(F.data.startswith("latex_padding_"))
async def cq_change_latex_padding(callback: CallbackQuery):
    """Обработчик для изменения отступа LaTeX."""
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    settings = await get_user_settings(user_id)
    current_padding = settings['latex_padding']

    action = callback.data.split('_')[-1]  # 'incr' or 'decr'
    new_padding = current_padding

    if action == "incr":
        new_padding += 5
    elif action == "decr":
        new_padding = max(0, current_padding - 5)

    if new_padding == current_padding:
        await callback.answer("Значение отступа не изменилось.")
        return

    settings['latex_padding'] = new_padding
    await update_user_settings_db(user_id, settings)

    keyboard = await get_settings_keyboard(user_id)
    await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
    await callback.answer(translator.gettext(lang, "settings_latex_padding_changed", padding=new_padding))

@router.callback_query(F.data.startswith("latex_dpi_"))
async def cq_change_latex_dpi(callback: CallbackQuery):
    """Обработчик для изменения DPI LaTeX."""
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    settings = await get_user_settings(user_id)
    current_dpi = settings.get('latex_dpi', 300) # Используем .get для безопасности

    action = callback.data.split('_')[-1]  # 'incr' or 'decr'
    new_dpi = current_dpi

    if action == "incr":
        new_dpi = min(600, current_dpi + 50)
    elif action == "decr":
        new_dpi = max(100, current_dpi - 50)

    if new_dpi == current_dpi:
        await callback.answer("Значение DPI не изменилось (достигнут лимит).")
        return

    settings['latex_dpi'] = new_dpi
    await update_user_settings_db(user_id, settings)

    keyboard = await get_settings_keyboard(user_id)
    await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
    await callback.answer(translator.gettext(lang, "settings_latex_dpi_changed", dpi=new_dpi))

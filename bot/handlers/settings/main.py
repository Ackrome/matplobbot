from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from shared_lib.database import get_user_settings, get_user_repos
from shared_lib.i18n import translator

router = Router()

AVAILABLE_LANGUAGES = {"en": "English", "ru": "Русский"}


async def get_settings_keyboard(user_id: int) -> InlineKeyboardBuilder:
    """Creates the main inline keyboard for user settings."""
    settings = await get_user_settings(user_id)
    lang = settings.get('language', 'en')
    builder = InlineKeyboardBuilder()

    # Docstring toggle
    docstring_status_key = "settings_docstring_on" if settings['show_docstring'] else "settings_docstring_off"
    builder.row(InlineKeyboardButton(
        text=translator.gettext(lang, "settings_show_docstring", status=translator.gettext(lang, docstring_status_key)),
        callback_data="settings_toggle_docstring"
    ))

    # Markdown display mode
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

    # LaTeX settings
    builder.row(
        InlineKeyboardButton(text="➖", callback_data="latex_padding_decr"),
        InlineKeyboardButton(text=translator.gettext(lang, "settings_latex_padding", padding=settings['latex_padding']), callback_data="noop"),
        InlineKeyboardButton(text="➕", callback_data="latex_padding_incr")
    )
    builder.row(
        InlineKeyboardButton(text="➖", callback_data="latex_dpi_decr"),
        InlineKeyboardButton(text=translator.gettext(lang, "settings_latex_dpi", dpi=settings['latex_dpi']), callback_data="noop"),
        InlineKeyboardButton(text="➕", callback_data="latex_dpi_incr")
    )

    # GitHub Repositories
    user_repos = await get_user_repos(user_id)
    repo_button_key = "settings_manage_repos_btn" if user_repos else "settings_add_repos_btn"
    builder.row(InlineKeyboardButton(text=translator.gettext(lang, repo_button_key), callback_data="manage_repos"))

    # Language Setting
    current_lang_name = AVAILABLE_LANGUAGES.get(lang, "Unknown")
    builder.row(InlineKeyboardButton(text=translator.gettext(lang, "settings_language_btn", lang_name=current_lang_name), callback_data="settings_cycle_language"))

    # Schedule Subscriptions
    builder.row(InlineKeyboardButton(text=translator.gettext(lang, "settings_manage_subscriptions_btn"), callback_data="manage_subscriptions"))

    return builder


@router.message(Command('settings'))
async def command_settings(message: Message):
    """Handler for the /settings command."""
    user_id = message.from_user.id
    lang = await translator.get_user_language(user_id)
    keyboard = await get_settings_keyboard(user_id)
    await message.answer(translator.gettext(lang, "settings_menu_header"), reply_markup=keyboard.as_markup())


@router.callback_query(F.data == "back_to_settings")
async def cq_back_to_settings(callback: CallbackQuery):
    """Returns to the main settings menu."""
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    keyboard = await get_settings_keyboard(user_id)
    await callback.message.edit_text(translator.gettext(lang, "settings_menu_header"), reply_markup=keyboard.as_markup())
    await callback.answer()
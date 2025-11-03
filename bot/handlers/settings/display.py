from aiogram import F, Router
from aiogram.types import CallbackQuery

from shared_lib.database import get_user_settings, update_user_settings_db
from shared_lib.i18n import translator
from .main import get_settings_keyboard

router = Router()

MD_DISPLAY_MODES = ['md_file', 'html_file', 'pdf_file']


@router.callback_query(F.data == "settings_toggle_docstring")
async def cq_toggle_docstring(callback: CallbackQuery):
    """Handler for toggling the 'show_docstring' setting."""
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    settings = await get_user_settings(user_id)
    settings['show_docstring'] = not settings['show_docstring']
    await update_user_settings_db(user_id, settings)
    keyboard = await get_settings_keyboard(user_id)
    await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
    await callback.answer(translator.gettext(lang, "settings_docstring_updated"))


@router.callback_query(F.data == "settings_cycle_md_mode")
async def cq_cycle_md_mode(callback: CallbackQuery):
    """Handler for cycling through Markdown display modes."""
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    settings = await get_user_settings(user_id)

    current_mode = settings.get('md_display_mode', 'md_file')
    try:
        current_index = MD_DISPLAY_MODES.index(current_mode)
        new_mode = MD_DISPLAY_MODES[(current_index + 1) % len(MD_DISPLAY_MODES)]
    except ValueError:
        new_mode = MD_DISPLAY_MODES[0]

    settings['md_display_mode'] = new_mode
    await update_user_settings_db(user_id, settings)

    keyboard = await get_settings_keyboard(user_id)
    await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())

    md_mode_map = {'md_file': 'settings_md_mode_md', 'html_file': 'settings_md_mode_html', 'pdf_file': 'settings_md_mode_pdf'}
    mode_text = translator.gettext(lang, md_mode_map.get(new_mode, 'settings_md_mode_unknown'))
    await callback.answer(translator.gettext(lang, "settings_md_mode_updated", mode_text=mode_text))
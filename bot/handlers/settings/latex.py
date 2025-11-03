from aiogram import F, Router
from aiogram.types import CallbackQuery

from shared_lib.database import get_user_settings, update_user_settings_db
from shared_lib.i18n import translator
from .main import get_settings_keyboard

router = Router()


@router.callback_query(F.data.startswith("latex_padding_"))
async def cq_change_latex_padding(callback: CallbackQuery):
    """Handler for changing LaTeX padding."""
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    settings = await get_user_settings(user_id)
    current_padding = settings['latex_padding']

    action = callback.data.split('_')[-1]
    new_padding = max(0, current_padding + 5) if action == "incr" else max(0, current_padding - 5)

    if new_padding == current_padding:
        await callback.answer("Padding value did not change.")
        return

    settings['latex_padding'] = new_padding
    await update_user_settings_db(user_id, settings)

    keyboard = await get_settings_keyboard(user_id)
    await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
    await callback.answer(translator.gettext(lang, "settings_latex_padding_changed", padding=new_padding))


@router.callback_query(F.data.startswith("latex_dpi_"))
async def cq_change_latex_dpi(callback: CallbackQuery):
    """Handler for changing LaTeX DPI."""
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    settings = await get_user_settings(user_id)
    current_dpi = settings.get('latex_dpi', 300)

    action = callback.data.split('_')[-1]
    new_dpi = min(600, current_dpi + 50) if action == "incr" else max(100, current_dpi - 50)

    if new_dpi == current_dpi:
        await callback.answer("DPI value did not change (limit reached).")
        return

    settings['latex_dpi'] = new_dpi
    await update_user_settings_db(user_id, settings)

    keyboard = await get_settings_keyboard(user_id)
    await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
    await callback.answer(translator.gettext(lang, "settings_latex_dpi_changed", dpi=new_dpi))
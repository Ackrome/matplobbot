from aiogram import F, Router
from aiogram.types import CallbackQuery

from shared_lib.database import get_user_settings, update_user_settings_db
from shared_lib.i18n import translator
from .main import get_settings_keyboard, AVAILABLE_LANGUAGES

router = Router()

LANGUAGE_CODES = list(AVAILABLE_LANGUAGES.keys())


@router.callback_query(F.data == "settings_cycle_language")
async def cq_cycle_language(callback: CallbackQuery):
    """Cycles through available languages."""
    user_id = callback.from_user.id
    settings = await get_user_settings(user_id)
    current_lang = settings.get('language', 'en')

    try:
        current_index = LANGUAGE_CODES.index(current_lang)
        new_lang = LANGUAGE_CODES[(current_index + 1) % len(LANGUAGE_CODES)]
    except ValueError:
        new_lang = LANGUAGE_CODES[0]

    settings['language'] = new_lang
    await update_user_settings_db(user_id, settings)

    keyboard = await get_settings_keyboard(user_id)
    await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
    await callback.answer(translator.gettext(new_lang, "settings_language_updated", lang_name=AVAILABLE_LANGUAGES[new_lang]))
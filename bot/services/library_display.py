import logging
from aiogram.types import Message
import matplobblib
from .. import keyboards as kb, database
from ..i18n import translator


async def show_code_by_path(message: Message, user_id: int, code_path: str, header: str):
    """Helper function to send code to the user based on its path."""
    try:
        lang = await translator.get_user_language(user_id)
        submodule, topic, code_name = code_path.split('.')
        
        module = matplobblib._importlib.import_module(f'matplobblib.{submodule}')

        # Определяем, показывать ли docstring, на основе настроек пользователя
        settings = await database.get_user_settings(user_id)
        dict_name = 'themes_list_dicts_full' if settings['show_docstring'] else 'themes_list_dicts_full_nd'
        code_dictionary = getattr(module, dict_name)

        repl = code_dictionary[topic][code_name]

        await message.answer(f'{header}: \n{code_path.replace(".", " -> ")}')
        
        if len(repl) > 4096:
            await message.answer('Сообщение будет отправлено в нескольких частях')
            for x in range(0, len(repl), 4096):
                await message.answer(f'''```python\n{repl[x:x+4096]}\n```''', parse_mode='markdown')
        else:
            await message.answer(f'''```python\n{repl}\n```''', parse_mode='markdown')
        
        await message.answer(translator.gettext(lang, "what_to_do_next"), reply_markup=kb.get_code_action_keyboard(code_path))
        await message.answer(translator.gettext(lang, "or_choose_another_command"), reply_markup=await kb.get_main_reply_keyboard(user_id))

    except (ValueError, KeyError, AttributeError, ImportError) as e:
        logging.error(f"Ошибка при показе кода (path: {code_path}): {e}")
        await message.answer(translator.gettext(await translator.get_user_language(user_id), "show_code_error"))
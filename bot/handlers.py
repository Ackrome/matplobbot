import logging

from aiogram import F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database
import asyncio
import sys
import matplobblib
import os
import pkg_resources

# from main import logging

import keyboards as kb

async def update_library_async(library_name):
    try:
        process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "pip", "install", "--upgrade", library_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            print(f"Библиотека '{library_name}' успешно обновлена! {stdout.decode()}")
            return True, f"Библиотека '{library_name}' успешно обновлена! Текущая версия: {pkg_resources.get_distribution('matplobblib').version}"
        else:
            print(f"Ошибка при обновлении библиотеки '{library_name}': {stderr.decode()}")
            return False, f"Ошибка при обновлении библиотеки '{library_name}': {stderr.decode()}"
    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")
        return False, f"Произошла непредвиденная ошибка: {e}"


router = Router()

# --- User Settings Defaults ---
# Эти настройки используются по умолчанию, если для пользователя нет записи в БД
# или если конкретная настройка отсутствует в его записи.
DEFAULT_SETTINGS = {
    'show_docstring': True,
}

# Теперь эта функция асинхронная, так как обращается к БД
async def get_user_settings(user_id: int) -> dict:
    """Получает настройки для пользователя из БД, объединяя их с настройками по умолчанию."""
    db_settings = await database.get_user_settings_db(user_id)
    merged_settings = DEFAULT_SETTINGS.copy()
    merged_settings.update(db_settings) # Настройки из БД переопределяют дефолтные
    return merged_settings


@router.message(CommandStart())
async def comand_start(message: Message):
    await message.answer(
        f'Привет, {message.from_user.full_name}!',
        reply_markup=kb.help
    )
    
@router.message(Command('help'))
async def comand_help(message: Message):
    await message.answer('Вы просите помощи? Не нужно. ее не будет.')

##################################################################################################
# ASK
##################################################################################################
class Search(StatesGroup):
    submodule = State()
    topic = State()
    code = State()


@router.message(Command('ask'))
async def ask(message: Message, state: FSMContext):
    await state.set_state(Search.submodule)
    await message.answer('Введите ваш вопрос', reply_markup=kb.submodules)

@router.message(Search.submodule)
async def process_submodule(message: Message, state: FSMContext):
    # Проверяем, что введённый подмодуль является ожидаемым
    if message.text not in matplobblib.submodules:
        await message.answer("Неверный выбор. Попробуйте еще раз.", reply_markup=kb.submodules)
        return
    await state.update_data(submodule=message.text)
    # Импортируем модуль для получения списка тем
    module = matplobblib._importlib.import_module(f'matplobblib.{message.text}')

    settings = await get_user_settings(message.from_user.id) # Теперь асинхронный вызов
    # В зависимости от настроек пользователя, выбираем нужный словарь в библиотеке
    dict_name = 'themes_list_dicts_full' if settings.get('show_docstring', True) else 'themes_list_dicts_full_nd'
    code_dictionary = getattr(module, dict_name)
    topics = list(code_dictionary.keys())
    await state.set_state(Search.topic)
    await message.answer("Введите тему", reply_markup=kb.topics_dict[message.text][0])

@router.message(Search.topic)
async def process_topic(message: Message, state: FSMContext):
    data = await state.get_data()
    submodule = data["submodule"]
    module = matplobblib._importlib.import_module(f'matplobblib.{submodule}')

    settings = await get_user_settings(message.from_user.id) # Теперь асинхронный вызов
    dict_name = 'themes_list_dicts_full' if settings.get('show_docstring', True) else 'themes_list_dicts_full_nd'
    code_dictionary = getattr(module, dict_name)
    topics = list(code_dictionary.keys())
    # Если тема не входит в ожидаемые, просим попробовать снова
    if message.text not in topics:
        await message.answer("Неверный выбор. Попробуйте еще раз.", reply_markup=kb.topics_dict[submodule][0])
        return
    await state.update_data(topic=message.text)
    await state.set_state(Search.code)
    await message.answer("Выберите задачу", reply_markup=kb.topics_dict[submodule][1][message.text])

@router.message(Search.code)
async def process_code(message: Message, state: FSMContext):
    data = await state.get_data()
    submodule = data["submodule"]
    topic = data["topic"]
    module = matplobblib._importlib.import_module(f'matplobblib.{submodule}')

    settings = await get_user_settings(message.from_user.id) # Теперь асинхронный вызов
    # В зависимости от настроек пользователя, выбираем нужный словарь в библиотеке
    dict_name = 'themes_list_dicts_full' if settings.get('show_docstring', True) else 'themes_list_dicts_full_nd'
    code_dictionary = getattr(module, dict_name)

    possible_codes = list(code_dictionary[topic].keys())
    # Если выбранная задача не входит в ожидаемые, просим повторить выбор
    if message.text not in possible_codes:
        await message.answer("Неверный выбор. Попробуйте еще раз.", reply_markup=kb.topics_dict[submodule][1][topic])
        return
    await state.update_data(code=message.text)
    data = await state.get_data()
    await message.answer(f'Ваш запрос: \n{submodule} \n{topic} \n{data["code"]}')
    repl = code_dictionary[topic][data["code"]]
    if len(repl) > 4096:
        await message.answer('Сообщение будет отправлено в нескольких частях')
        for x in range(0, len(repl), 4096):
            await message.answer(f'''```python\n{repl[x:x+4096]}\n```''',
                                 parse_mode='markdown',
                                 reply_markup=kb.help)
    else:
        await message.answer(f'''```python\n{repl}\n```''',
                             parse_mode='markdown',
                             reply_markup=kb.help)
    await state.clear()
##################################################################################################
# UPDATE
##################################################################################################
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID'))

@router.message(Command('update'))
async def update(message: Message):
    if message.from_user.id != ADMIN_USER_ID:
        await message.reply("У вас нет прав на использование этой команды.", reply_markup=kb.help)
        return

    status_msg = await message.answer("Начинаю обновление библиотеки `matplobblib`...")
    # Можно добавить 
    # await message.answer_chat_action("typing")
    success, status_message_text = await update_library_async('matplobblib')
    if success:
        # Перезагрузка модуля matplobblib, если это необходимо для немедленного применения изменений
        import importlib
        importlib.reload(matplobblib) # Может быть сложным и иметь побочные эффекты
        await status_msg.edit_text(status_message_text) # Убран reply_markup
    else:
        await status_msg.edit_text(status_message_text) # Убран reply_markup

##################################################################################################
# SETTINGS
##################################################################################################

# Теперь эта функция асинхронная, так как обращается к БД
async def get_settings_keyboard(user_id: int) -> InlineKeyboardBuilder:
    """Создает инлайн-клавиатуру для настроек пользователя."""
    settings = await get_user_settings(user_id) # Теперь асинхронный вызов
    builder = InlineKeyboardBuilder()

    show_docstring_status = "✅ Вкл" if settings.get('show_docstring', True) else "❌ Выкл"

    builder.row(
        InlineKeyboardButton(
            text=f"Показывать описание: {show_docstring_status}",
            callback_data="settings_toggle_docstring"
        )
    )
    # Здесь можно добавлять новые настройки
    return builder

@router.message(Command('settings'))
async def command_settings(message: Message):
    """Обработчик команды /settings."""
    keyboard = await get_settings_keyboard(message.from_user.id) # Теперь асинхронный вызов
    await message.answer(
        "⚙️ Настройки пользователя:",
        reply_markup=keyboard.as_markup()
    )

@router.callback_query(F.data == "settings_toggle_docstring")
async def cq_toggle_docstring(callback: CallbackQuery):
    """Обработчик для переключения настройки 'show_docstring'."""
    user_id = callback.from_user.id
    settings = await get_user_settings(user_id) # Теперь асинхронный вызов
    settings['show_docstring'] = not settings.get('show_docstring', True)
    await database.update_user_settings_db(user_id, settings) # Сохраняем обновленные настройки в БД
    keyboard = await get_settings_keyboard(user_id) # Теперь асинхронный вызов
    await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
    await callback.answer("Настройка 'Показывать описание' обновлена.")
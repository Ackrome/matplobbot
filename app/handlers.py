from aiogram import F, Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import subprocess
import sys
import matplobblib

from app import keyboards as kb


async def update_library(library_name):
    try:
        # Выполняем команду pip install --upgrade для обновления библиотеки
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", library_name])
        print(f"Библиотека '{library_name}' успешно обновлена!")
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при обновлении библиотеки '{library_name}': {e}")
    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")

router = Router()



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
    await message.answer('Введите ваш вопрос',
                         reply_markup = kb.submodules
                         )
    
@router.message(Search.submodule)
async def ask(message: Message, state: FSMContext):
    await state.update_data(submodule=message.text)
    await state.set_state(Search.topic)
    await message.answer('Введите тему',
                         reply_markup=kb.topics_dict[message.text][0]
                         )

@router.message(Search.topic)
async def ask(message: Message, state: FSMContext):
    await state.update_data(topic=message.text)
    data = await state.get_data()
    await state.set_state(Search.code)
    await message.answer('Выберите задачу',
                         reply_markup=kb.topics_dict[data["submodule"]][1][data["topic"]]
                         )

@router.message(Search.code)
async def ask(message: Message, state: FSMContext):
    await state.update_data(code=message.text)
    data = await state.get_data()
    await message.answer(f'Ваш запрос: \n {data["submodule"]} \n {data["topic"]} \n {data["code"]}')
    repl = matplobblib._importlib.import_module(f'matplobblib.{data["submodule"]}').themes_list_dicts_full[data["topic"]][data["code"]]
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
@router.message(Command('update'))
async def update(message: Message):
    await update_library('matplobblib')
    await message.reply(f'Библиотека успешно обновлена!', reply_markup=kb.help)
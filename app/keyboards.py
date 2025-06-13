from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
import matplobblib

commands = ['/ask','/update']

help = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=i)] for i in commands],
    resize_keyboard=True,
    input_field_placeholder='Что выберем, хозяин?',
    one_time_keyboard=True
)


submodules = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=i)] for i in matplobblib.submodules + commands],
    resize_keyboard=True,
    input_field_placeholder='Что выберем, хозяин?',
    one_time_keyboard=True
)
    
topics_dict = dict()
for el in range(len(matplobblib.submodules)):
    module = matplobblib._importlib.import_module(f'matplobblib.{matplobblib.submodules[el]}')
    topics_dict[matplobblib.submodules[el]] = [ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=i)] for i in list(module.themes_list_dicts_full.keys()) + commands],
        resize_keyboard=True,
        input_field_placeholder='Что выберем, хозяин?',
        one_time_keyboard=True
    ),
    {key: ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=i)] for i in list(module.themes_list_dicts_full[key].keys()) + commands],
        resize_keyboard=True,
        input_field_placeholder='Что выберем, хозяин?',
        one_time_keyboard=True
    ) for key in list(module.themes_list_dicts_full.keys())}]
    
    

import logging
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import matplobblib

logger = logging.getLogger(__name__)

commands = ['/ask','/update']

logger.debug(f"Генерация клавиатуры 'help' с командами: {commands}")
help = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=i)] for i in commands],
    resize_keyboard=True,
    input_field_placeholder='Что выберем, хозяин?',
    one_time_keyboard=True
)
logger.debug(f"Генерация клавиатуры 'submodules'. Базовые команды: {commands}, подмодули matplobblib: {matplobblib.submodules}")
submodules = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=i)] for i in matplobblib.submodules + commands],
    resize_keyboard=True,
    input_field_placeholder='Что выберем, хозяин?',
    one_time_keyboard=True
)

logger.info("Начало генерации клавиатур 'topics_dict'.")
topics_dict = dict()
for el in range(len(matplobblib.submodules)):
    submodule_name = matplobblib.submodules[el]
    logger.debug(f"Обработка подмодуля: {submodule_name} для topics_dict.")
    try:
        module = matplobblib._importlib.import_module(f'matplobblib.{submodule_name}')
        module_topics = list(module.themes_list_dicts_full.keys())
        logger.debug(f"Темы для {submodule_name}: {module_topics}")

        topics_keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=i)] for i in module_topics + commands],
            resize_keyboard=True,
            input_field_placeholder='Что выберем, хозяин?',
            one_time_keyboard=True
        )
        sub_topics_keyboards = {
            key: ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text=i)] for i in list(module.themes_list_dicts_full[key].keys()) + commands],
                resize_keyboard=True,
                input_field_placeholder='Что выберем, хозяин?',
                one_time_keyboard=True
            ) for key in module_topics
        }
        topics_dict[submodule_name] = [topics_keyboard, sub_topics_keyboards]
        logger.debug(f"Успешно сгенерированы клавиатуры для подмодуля: {submodule_name}")
    except Exception as e:
        logger.error(f"Ошибка генерации клавиатур для подмодуля {submodule_name}: {e}", exc_info=True)

logger.info("Завершение генерации клавиатур 'topics_dict'.")

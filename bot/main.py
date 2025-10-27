import asyncio
import logging
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
import aiohttp

from .handlers import router
from .logger import UserLoggingMiddleware # Импортируем middleware
from .database import init_db, init_db_pool # Импортируем функции инициализации БД
from .services.university_api import setup_ruz_api_client

# Загрузка переменных окружения и настройка логгирования из app.logger
load_dotenv()
from . import logger # Импорт для инициализации настроек логгирования

BOT_TOKEN = os.getenv('BOT_TOKEN')

# Асинхронная функция для запуска бота
async def main():
    # Инициализируем пул соединений с БД
    await init_db_pool()

    # Инициализируем базу данных перед запуском бота
    await init_db()

    with aiohttp.ClientSession() as session:
        setup_ruz_api_client(session)        # Инициализируем RUZ API клиент
        
        bot = Bot(BOT_TOKEN)
        dp = Dispatcher()
        dp.update.middleware(UserLoggingMiddleware())
        dp.include_router(router)
        
        await dp.start_polling(bot)



if __name__ == '__main__':
    try:
        # Запускаем асинхронного бота в основном потоке
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.error('Bot stopped!')
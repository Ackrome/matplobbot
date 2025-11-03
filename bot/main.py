import asyncio
import logging
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
import aiohttp
from .handlers import setup_handlers
from .logger import UserLoggingMiddleware
from shared_lib.database import init_db, init_db_pool
from shared_lib.services.university_api import create_ruz_api_client

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

    # Устанавливаем общий таймаут для всех запросов в сессии
    timeout = aiohttp.ClientTimeout(total=60) # Increased timeout to 60 seconds
    async with aiohttp.ClientSession(timeout=timeout) as session:
        bot = Bot(BOT_TOKEN)
        ruz_api_client_instance = create_ruz_api_client(session) # Создаем экземпляр клиента

        dp = Dispatcher()
        dp.update.middleware(UserLoggingMiddleware())
        
        setup_handlers(dp, ruz_api_client=ruz_api_client_instance)
        await dp.start_polling(bot)



if __name__ == '__main__':
    try:
        # Запускаем асинхронного бота в основном потоке
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.error('Bot stopped!')
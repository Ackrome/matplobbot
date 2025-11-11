import asyncio
import logging
import os
import aiohttp
import requests
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types


\
from .handlers import setup_handlers
from .middleware import GroupMentionCommandMiddleware
from shared_lib.i18n import translator
from .logger import UserLoggingMiddleware
from shared_lib.database import init_db, init_db_pool
from aiogram import Dispatcher
from shared_lib.services.university_api import create_ruz_api_client

# Загрузка переменных окружения и настройка логгирования из app.logger
load_dotenv()

from . import logger # Импорт для инициализации настроек логгирования

BOT_TOKEN = os.getenv('BOT_TOKEN')

async def set_bot_commands(bot: Bot):
    """Sets the bot's command list in the UI for different user scopes."""
    
    # Define commands for regular users (in both languages)
    user_commands_ru = [
        types.BotCommand(command="start", description=translator.gettext("ru", "command_desc_start")),
        types.BotCommand(command="help", description=translator.gettext("ru", "help_btn_help").split(' - ')[1]),
        types.BotCommand(command="schedule", description=translator.gettext("ru", "help_btn_schedule").split(' - ')[1]),
        types.BotCommand(command="myschedule", description=translator.gettext("ru", "help_btn_myschedule").split(' - ')[1]),
        types.BotCommand(command="matp_all", description=translator.gettext("ru", "help_btn_matp_all").split(' - ')[1]),
        types.BotCommand(command="matp_search", description=translator.gettext("ru", "help_btn_matp_search").split(' - ')[1]),
        types.BotCommand(command="lec_all", description=translator.gettext("ru", "help_btn_lec_all").split(' - ')[1]),
        types.BotCommand(command="lec_search", description=translator.gettext("ru", "help_btn_lec_search").split(' - ')[1]),
        types.BotCommand(command="favorites", description=translator.gettext("ru", "help_btn_favorites").split(' - ')[1]),
        types.BotCommand(command="settings", description=translator.gettext("ru", "help_btn_settings").split(' - ')[1]),
        types.BotCommand(command="latex", description=translator.gettext("ru", "help_btn_latex").split(' - ')[1]),
        types.BotCommand(command="mermaid", description=translator.gettext("ru", "help_btn_mermaid").split(' - ')[1]),
        types.BotCommand(command="offershorter", description=translator.gettext("ru", "help_btn_offershorter").split(' - ')[1]),
        types.BotCommand(command="cancel", description=translator.gettext("ru", "command_desc_cancel")),
    ]
    
    user_commands_en = [
        types.BotCommand(command="start", description=translator.gettext("en", "command_desc_start")),
        types.BotCommand(command="help", description=translator.gettext("en", "help_btn_help").split(' - ')[1]),
        types.BotCommand(command="schedule", description=translator.gettext("en", "help_btn_schedule").split(' - ')[1]),
        types.BotCommand(command="myschedule", description=translator.gettext("en", "help_btn_myschedule").split(' - ')[1]),
        types.BotCommand(command="matp_all", description=translator.gettext("en", "help_btn_matp_all").split(' - ')[1]),
        types.BotCommand(command="matp_search", description=translator.gettext("en", "help_btn_matp_search").split(' - ')[1]),
        types.BotCommand(command="lec_all", description=translator.gettext("en", "help_btn_lec_all").split(' - ')[1]),
        types.BotCommand(command="lec_search", description=translator.gettext("en", "help_btn_lec_search").split(' - ')[1]),
        types.BotCommand(command="favorites", description=translator.gettext("en", "help_btn_favorites").split(' - ')[1]),
        types.BotCommand(command="settings", description=translator.gettext("en", "help_btn_settings").split(' - ')[1]),
        types.BotCommand(command="latex", description=translator.gettext("en", "help_btn_latex").split(' - ')[1]),
        types.BotCommand(command="mermaid", description=translator.gettext("en", "help_btn_mermaid").split(' - ')[1]),
        types.BotCommand(command="offershorter", description=translator.gettext("en", "help_btn_offershorter").split(' - ')[1]),
        types.BotCommand(command="cancel", description=translator.gettext("en", "command_desc_cancel")),
    ]

    # Set commands for all private chats (default scope)
    await bot.set_my_commands(user_commands_ru, scope=types.BotCommandScopeAllPrivateChats(), language_code="ru")
    await bot.set_my_commands(user_commands_en, scope=types.BotCommandScopeAllPrivateChats(), language_code="en")
    
    logging.info("Default user commands have been set.")

# Асинхронная функция для запуска бота
async def main():
    # Graceful shutdown handler
    async def on_shutdown(dispatcher: Dispatcher):
        logging.warning("Shutting down...")
        await dispatcher.storage.close()
        await bot.session.close()


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
        dp.shutdown.register(on_shutdown)
        dp.update.outer_middleware(GroupMentionCommandMiddleware()) # Register the new middleware
        dp.update.middleware(UserLoggingMiddleware())
        
        setup_handlers(dp, bot=bot, ruz_api_client=ruz_api_client_instance)
        
        # Set the bot commands on startup
        await set_bot_commands(bot)
        await dp.start_polling(bot)



if __name__ == '__main__':
    try:
        # Запускаем асинхронного бота в основном потоке
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.error('Bot stopped!')
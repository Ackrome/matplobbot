import asyncio
import logging
import os

import aiohttp
from dotenv import load_dotenv

load_dotenv()

# --- ПАТЧ ДЛЯ СИНХРОННЫХ ЗАПРОСОВ (requests / matplobblib) ---
# Устанавливаем прокси в ОС до импорта хендлеров, чтобы requests подхватил его
PROXY_URL = os.getenv("PROXY_URL")
if PROXY_URL:
    # Меняем socks5:// на socks5h:// -> буква 'h' заставит прокси
    # самостоятельно резолвить DNS (api.github.com), что решит проблему [Errno -3]
    socks5h_proxy = PROXY_URL.replace("socks5://", "socks5h://")
    os.environ["HTTP_PROXY"] = socks5h_proxy
    os.environ["HTTPS_PROXY"] = socks5h_proxy
    os.environ["ALL_PROXY"] = socks5h_proxy

from aiogram import Bot, Dispatcher, types
from aiogram.client.session.aiohttp import AiohttpSession

from shared_lib.database import init_db_pool
from shared_lib.i18n import translator
from shared_lib.services.university_api import create_ruz_api_client

# Импорт вашего конфига логгера
from .handlers import setup_handlers
from .logger import UserLoggingMiddleware
from .middleware import GroupMentionCommandMiddleware
from .services.search_utils import index_matplobblib_library

BOT_TOKEN = os.getenv("BOT_TOKEN")


def get_cmd_desc(lang: str, key: str) -> str:
    """
    Безопасно извлекает описание команды из перевода.
    Ожидает формат 'Icon /command - Description'.
    Если разделителя ' - ' нет, возвращает всю строку.
    """
    text = translator.gettext(lang, key)
    parts = text.split(" - ")
    if len(parts) > 1:
        return parts[1]
    return text


async def set_bot_commands(bot: Bot):
    """Sets the bot's command list in the UI for different user scopes."""

    # Define commands for regular users (in both languages)
    user_commands_ru = [
        types.BotCommand(
            command="start", description=translator.gettext("ru", "command_desc_start")
        ),
        types.BotCommand(command="help", description=get_cmd_desc("ru", "help_btn_help")),
        types.BotCommand(command="schedule", description=get_cmd_desc("ru", "help_btn_schedule")),
        types.BotCommand(
            command="myschedule", description=get_cmd_desc("ru", "help_btn_myschedule")
        ),
        types.BotCommand(command="matp_all", description=get_cmd_desc("ru", "help_btn_matp_all")),
        types.BotCommand(
            command="matp_search", description=get_cmd_desc("ru", "help_btn_matp_search")
        ),
        types.BotCommand(command="lec_all", description=get_cmd_desc("ru", "help_btn_lec_all")),
        types.BotCommand(
            command="lec_search", description=get_cmd_desc("ru", "help_btn_lec_search")
        ),
        types.BotCommand(command="favorites", description=get_cmd_desc("ru", "help_btn_favorites")),
        types.BotCommand(command="settings", description=get_cmd_desc("ru", "help_btn_settings")),
        types.BotCommand(command="latex", description=get_cmd_desc("ru", "help_btn_latex")),
        types.BotCommand(command="mermaid", description=get_cmd_desc("ru", "help_btn_mermaid")),
        types.BotCommand(
            command="offershorter", description=get_cmd_desc("ru", "help_btn_offershorter")
        ),
        types.BotCommand(
            command="cancel", description=translator.gettext("ru", "command_desc_cancel")
        ),
    ]

    user_commands_en = [
        types.BotCommand(
            command="start", description=translator.gettext("en", "command_desc_start")
        ),
        types.BotCommand(command="help", description=get_cmd_desc("en", "help_btn_help")),
        types.BotCommand(command="schedule", description=get_cmd_desc("en", "help_btn_schedule")),
        types.BotCommand(
            command="myschedule", description=get_cmd_desc("en", "help_btn_myschedule")
        ),
        types.BotCommand(command="matp_all", description=get_cmd_desc("en", "help_btn_matp_all")),
        types.BotCommand(
            command="matp_search", description=get_cmd_desc("en", "help_btn_matp_search")
        ),
        types.BotCommand(command="lec_all", description=get_cmd_desc("en", "help_btn_lec_all")),
        types.BotCommand(
            command="lec_search", description=get_cmd_desc("en", "help_btn_lec_search")
        ),
        types.BotCommand(command="favorites", description=get_cmd_desc("en", "help_btn_favorites")),
        types.BotCommand(command="settings", description=get_cmd_desc("en", "help_btn_settings")),
        types.BotCommand(command="latex", description=get_cmd_desc("en", "help_btn_latex")),
        types.BotCommand(command="mermaid", description=get_cmd_desc("en", "help_btn_mermaid")),
        types.BotCommand(
            command="offershorter", description=get_cmd_desc("en", "help_btn_offershorter")
        ),
        types.BotCommand(
            command="cancel", description=translator.gettext("en", "command_desc_cancel")
        ),
    ]

    try:
        # Set commands for all private chats (default scope)
        await bot.set_my_commands(
            user_commands_ru, scope=types.BotCommandScopeAllPrivateChats(), language_code="ru"
        )
        await bot.set_my_commands(
            user_commands_en, scope=types.BotCommandScopeAllPrivateChats(), language_code="en"
        )
        logging.info("Default user commands have been set.")
    except Exception as e:
        # Логируем ошибку, но не роняем бота. Команды могут не обновиться, но бот должен работать.
        logging.error(f"Failed to set bot commands: {e}")


async def main():
    # Настраиваем сессию СПЕЦИАЛЬНО для Telegram-бота
    if PROXY_URL:
        # ИСПРАВЛЕНИЕ: здесь используем logging.info вместо logger.info
        logging.info(f"Using proxy for bot: {PROXY_URL}")
        bot_session = AiohttpSession(timeout=600, proxy=PROXY_URL)
    else:
        bot_session = AiohttpSession(timeout=600)

    bot = Bot(BOT_TOKEN, session=bot_session)

    async def on_shutdown(dispatcher: Dispatcher):
        logging.warning("Shutting down...")
        await dispatcher.storage.close()
        await bot.session.close()

    await init_db_pool()

    # --- Создаем ОТДЕЛЬНУЮ сессию для RUZ API ---
    timeout_client = aiohttp.ClientTimeout(total=600)
    async with aiohttp.ClientSession(timeout=timeout_client) as ruz_session:
        ruz_api_client_instance = create_ruz_api_client(ruz_session)

        dp = Dispatcher()
        dp.shutdown.register(on_shutdown)
        dp.update.outer_middleware(GroupMentionCommandMiddleware())
        dp.update.middleware(UserLoggingMiddleware())

        setup_handlers(dp, bot=bot, ruz_api_client=ruz_api_client_instance)

        await set_bot_commands(bot)

        logging.info("Building semantic search index...")
        asyncio.create_task(index_matplobblib_library())
        logging.info("Semantic index built.")

        await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.error("Bot stopped!")

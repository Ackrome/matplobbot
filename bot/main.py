import asyncio
import logging
import os
from contextlib import suppress

import aiohttp
from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, types
from aiogram.exceptions import TelegramNetworkError

from shared_lib.database import init_db_pool
from shared_lib.egress import (
    configure_process_http_proxy_env,
    get_global_http_proxy_url,
    get_telegram_proxy_url,
)
from shared_lib.i18n import translator
from shared_lib.services.university_api import create_ruz_api_client
from shared_lib.telegram_bot_session import TelegramBotSession
from shared_lib.telegram_http import normalize_proxy_url
from shared_lib.telegram_polling import run_polling_with_retry
from shared_lib.telemetry import configure_service_telemetry

from .handlers import setup_handlers
from .logger import UserLoggingMiddleware
from .middleware import GroupMentionCommandMiddleware
from .services.search_utils import index_matplobblib_library
from .tracing import BotTracingMiddleware

BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_PROXY_URL = get_telegram_proxy_url()
POLLING_RETRY_DELAY_SECONDS = float(os.getenv("BOT_POLLING_RETRY_DELAY_SECONDS", "15"))

configure_process_http_proxy_env(
    get_global_http_proxy_url(),
    no_proxy_hosts=("ruz.fa.ru",),
)
configure_service_telemetry("matplobbot-bot")


def get_cmd_desc(lang: str, key: str) -> str:
    """
    Safely extracts a command description from a translation string.
    Expected format: 'Icon /command - Description'.
    If the delimiter is missing, returns the full string.
    """
    text = translator.gettext(lang, key)
    parts = text.split(" - ")
    if len(parts) > 1:
        return parts[1]
    return text


async def set_bot_commands(bot: Bot):
    """Sets the bot's command list in the UI for different user scopes."""

    user_commands_ru = [
        types.BotCommand(
            command="start", description=translator.gettext("ru", "command_desc_start")
        ),
        types.BotCommand(command="help", description=get_cmd_desc("ru", "help_btn_help")),
        types.BotCommand(command="schedule", description=get_cmd_desc("ru", "help_btn_schedule")),
        types.BotCommand(
            command="myschedule", description=get_cmd_desc("ru", "help_btn_myschedule")
        ),
        types.BotCommand(command="studio", description=translator.gettext("ru", "command_desc_studio")),
        types.BotCommand(command="matp_all", description=get_cmd_desc("ru", "help_btn_matp_all")),
        types.BotCommand(
            command="matp_search", description=get_cmd_desc("ru", "help_btn_matp_search")
        ),
        types.BotCommand(command="search", description=get_cmd_desc("ru", "help_btn_search")),
        types.BotCommand(
            command="search_presets",
            description=get_cmd_desc("ru", "help_btn_search_presets"),
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
        types.BotCommand(command="studio", description=translator.gettext("en", "command_desc_studio")),
        types.BotCommand(command="matp_all", description=get_cmd_desc("en", "help_btn_matp_all")),
        types.BotCommand(
            command="matp_search", description=get_cmd_desc("en", "help_btn_matp_search")
        ),
        types.BotCommand(command="search", description=get_cmd_desc("en", "help_btn_search")),
        types.BotCommand(
            command="search_presets",
            description=get_cmd_desc("en", "help_btn_search_presets"),
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
        await bot.set_my_commands(
            user_commands_ru, scope=types.BotCommandScopeAllPrivateChats(), language_code="ru"
        )
        await bot.set_my_commands(
            user_commands_en, scope=types.BotCommandScopeAllPrivateChats(), language_code="en"
        )
        logging.info("Default user commands have been set.")
    except Exception as exc:
        logging.error("Failed to set bot commands: %s", exc)


async def run_bot_once(ruz_api_client_instance) -> None:
    normalized_proxy_url = normalize_proxy_url(TELEGRAM_PROXY_URL)
    if normalized_proxy_url:
        logging.info("Using proxy for bot: %s", normalized_proxy_url)
        bot_session = TelegramBotSession(timeout=600, proxy_url=normalized_proxy_url)
    else:
        bot_session = TelegramBotSession(timeout=600)

    bot = Bot(BOT_TOKEN, session=bot_session)
    dp = Dispatcher()
    dp.update.outer_middleware(BotTracingMiddleware())
    dp.update.outer_middleware(GroupMentionCommandMiddleware())
    dp.update.middleware(UserLoggingMiddleware())
    setup_handlers(dp, bot=bot, ruz_api_client=ruz_api_client_instance)

    try:
        await set_bot_commands(bot)
        await dp.start_polling(bot)
    finally:
        logging.warning("Shutting down...")
        with suppress(Exception):
            await dp.storage.close()
        with suppress(Exception):
            await bot.session.close()


async def main():
    await init_db_pool()

    logging.info("Building semantic search index...")
    asyncio.create_task(index_matplobblib_library())
    logging.info("Semantic index built.")

    timeout_client = aiohttp.ClientTimeout(total=600)
    async with aiohttp.ClientSession(timeout=timeout_client, trust_env=False) as ruz_session:
        ruz_api_client_instance = create_ruz_api_client(ruz_session)
        await run_polling_with_retry(
            lambda: run_bot_once(ruz_api_client_instance),
            retry_delay_seconds=POLLING_RETRY_DELAY_SECONDS,
            logger=logging.getLogger(__name__),
            retryable_exceptions=(TelegramNetworkError, aiohttp.ClientError, OSError),
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.error("Bot stopped!")

import asyncio
import hashlib
import importlib
import importlib.metadata
import json
import logging
import shlex
import sys

import matplobblib
from aiogram import Bot, Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command, Filter
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

# from main import logging
from shared_lib import database
from shared_lib.i18n import translator
from shared_lib.redis_client import redis_client
from shared_lib.services.broadcast_service import (
    DEFAULT_BROADCAST_ACTIVE_DAYS,
    DEFAULT_BROADCAST_RATE_PER_SECOND,
    broadcast_chunks_to_users,
    format_broadcast_plan,
    format_broadcast_result,
    load_broadcast_text,
    normalize_broadcast_rate,
    split_telegram_message,
)

from .. import github_service
from .. import keyboards as kb
from ..config import ADMIN_USER_IDS

BROADCAST_USAGE = (
    "Usage:\n"
    "/broadcast_release [--execute] [--active-days N] [--rate N] [--limit N] "
    "[--user-id ID] [--file PATH]\n\n"
    "Without --execute the command only previews the broadcast plan. "
    "Default sources are docs/announcement.md when present and the current changelog."
)


class AdminPermissionError(Exception):
    """Custom exception for admin permission failures."""

    pass


class AdminFilter(Filter):
    """A filter to check if the user is the administrator."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user_id = event.from_user.id
        if user_id in ADMIN_USER_IDS:
            return True

        # If not an admin, raise an exception. This will be caught by an error handler
        # or the default dispatcher error handler, which is cleaner than sending a message here.
        # This also reliably stops further processing.
        raise AdminPermissionError("User is not an admin.")


class AdminOrCreatorFilter(Filter):
    """
    A filter to check if the user is an administrator or the creator of a group/supergroup chat.
    This is used for chat-specific administrative actions.
    """

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        chat = event.chat if isinstance(event, Message) else event.message.chat
        user_id = event.from_user.id

        # This filter is only for group/supergroup chats
        if chat.type not in ("group", "supergroup"):
            return False

        # Get chat member information
        member = await chat.get_member(user_id)

        # The user is authorized if they are the creator or an administrator
        return member.status in ("creator", "administrator")


class AdminManager:
    def __init__(self):
        self.router = Router()
        self._register_handlers()

    def _register_handlers(self):
        # Apply the AdminFilter directly to the command handlers
        self.router.message(Command("update"), AdminFilter())(self.update_command)
        self.router.message(Command("clear_cache"), AdminFilter())(self.clear_cache_command)
        self.router.message(Command("send_admin_summary"), AdminFilter())(
            self.send_admin_summary_command
        )
        self.router.message(Command("broadcast_release"), AdminFilter())(
            self.broadcast_release_command
        )
        self.router.message(Command("set_module"), AdminFilter())(self.set_module_command)
        self.router.message(Command("set_module"), AdminFilter())(self.set_module_command)

    def _parse_broadcast_command_args(self, text: str | None) -> tuple[dict | None, str | None]:
        try:
            tokens = shlex.split(text or "")
        except ValueError as exc:
            return None, f"Could not parse command options: {exc}"

        args = tokens[1:]
        options = {
            "execute": False,
            "active_days": DEFAULT_BROADCAST_ACTIVE_DAYS,
            "rate": DEFAULT_BROADCAST_RATE_PER_SECOND,
            "limit": None,
            "user_ids": [],
            "files": [],
        }

        index = 0
        while index < len(args):
            token = args[index]
            key = token
            value = None
            if token.startswith("--") and "=" in token:
                key, value = token.split("=", 1)

            if key == "--execute":
                options["execute"] = True
                index += 1
                continue

            if key not in {"--active-days", "--rate", "--limit", "--user-id", "--file"}:
                return None, f"Unknown option: {token}\n\n{BROADCAST_USAGE}"

            if value is None:
                index += 1
                if index >= len(args):
                    return None, f"Missing value for {key}\n\n{BROADCAST_USAGE}"
                value = args[index]

            try:
                if key == "--active-days":
                    options["active_days"] = max(1, int(value))
                elif key == "--rate":
                    options["rate"] = normalize_broadcast_rate(value)
                elif key == "--limit":
                    options["limit"] = max(1, int(value))
                elif key == "--user-id":
                    options["user_ids"].append(int(value))
                elif key == "--file":
                    options["files"].append(value)
            except ValueError:
                return None, f"Invalid value for {key}: {value}\n\n{BROADCAST_USAGE}"

            index += 1

        return options, None

    async def _send_broadcast_message(self, bot: Bot, user_id: int, text: str):
        try:
            await bot.send_message(user_id, text)
        except TelegramRetryAfter as exc:
            retry_after = float(getattr(exc, "retry_after", 1) or 1)
            await asyncio.sleep(retry_after + 1)
            await bot.send_message(user_id, text)

    async def _update_library_async(self, library_name: str, lang: str):
        try:
            # 1. Получаем старую версию через современный API
            try:
                old_version = importlib.metadata.version(library_name)
            except importlib.metadata.PackageNotFoundError:
                old_version = "not installed"

            # 2. Запускаем обновление через pip
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                library_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                # 3. Сбрасываем кэши поиска модулей (замена reload(pkg_resources))
                importlib.invalidate_caches()

                # 4. Получаем новую версию
                try:
                    new_version = importlib.metadata.version(library_name)
                except importlib.metadata.PackageNotFoundError:
                    new_version = "unknown"

                return True, translator.gettext(
                    lang,
                    "admin_update_success",
                    library_name=library_name,
                    old_version=old_version,
                    new_version=new_version,
                )
            else:
                error_text = stderr.decode().strip()
                logging.error(f"Error updating library '{library_name}': {error_text}")
                return False, translator.gettext(
                    lang, "admin_update_error", library_name=library_name, error=error_text
                )

        except Exception as e:
            logging.error(f"Unexpected error during library update: {e}", exc_info=True)
            return False, translator.gettext(lang, "admin_update_unexpected_error", error=str(e))

    async def update_command(self, message: Message):
        user_id = message.from_user.id
        # --- FIX: replaced get_user_language with get_language ---
        lang = await translator.get_language(user_id)
        status_msg = await message.answer(
            translator.gettext(lang, "admin_update_start", library_name="matplobblib")
        )
        success, status_message_text = await self._update_library_async("matplobblib", lang)

        if success:
            importlib.reload(matplobblib)
            await status_msg.edit_text(status_message_text)
        else:
            await status_msg.edit_text(status_message_text)

        await message.answer(
            translator.gettext(lang, "admin_update_finished"),
            reply_markup=await kb.get_main_reply_keyboard(user_id),
        )

    async def clear_cache_command(self, message: Message):
        user_id = message.from_user.id
        lang = await translator.get_language(user_id)
        status_msg = await message.answer(translator.gettext(lang, "admin_clear_cache_start"))

        await redis_client.clear_all_user_cache()
        kb.code_path_cache.clear()
        github_service.github_content_cache.clear()
        github_service.github_dir_cache.clear()
        await database.clear_latex_cache()

        await status_msg.edit_text(translator.gettext(lang, "admin_clear_cache_success"))
        await message.answer(
            translator.gettext(lang, "admin_clear_cache_finished"),
            reply_markup=await kb.get_main_reply_keyboard(user_id),
        )

    async def send_admin_summary_command(
        self, message: Message, bot: Bot, target_chat_id: int | None = None
    ):
        """
        This command can be called by a user or the scheduler.
        It fetches daily stats and pending suggestions, then sends them to the target chat.
        """
        # If a target_chat_id is provided (e.g., by the scheduler), use it.
        # Otherwise, use the ID of the user who sent the command.
        admin_id = target_chat_id or message.from_user.id

        lang = await translator.get_language(admin_id)

        summary_parts = []

        # 1. Fetch Daily Stats
        try:
            # ИСПОЛЬЗУЕМ get_session() ВМЕСТО get_db_connection_obj()
            async with database.get_session() as db:
                summary_data = await database.get_admin_daily_summary(db)
            summary_parts.append(
                translator.gettext(lang, "admin_daily_summary_text", **summary_data)
            )
        except Exception as e:
            logging.error(f"Failed to get admin daily summary stats: {e}", exc_info=True)
            summary_parts.append("❌ Не удалось загрузить статистику.")

        # 2. Fetch Pending Shorter Name Offers
        try:
            pending_offers_raw = await redis_client.client.lrange("pending_shorter_offers", 0, -1)
            if pending_offers_raw:
                summary_parts.append(
                    "\n\n" + translator.gettext(lang, "admin_summary_pending_offers_header")
                )

                for offer_raw in pending_offers_raw:
                    offer = json.loads(offer_raw)
                    notification_text = translator.gettext(
                        lang,
                        "shorter_name_admin_notification",
                        user_id=offer["user_id"],
                        user_name=offer["user_name"],
                        full_name=offer["full_name"],
                        short_name=offer["short_name"],
                    )

                    data_to_hash = f"{offer['user_id']}:{offer['full_name']}:{offer['short_name']}"
                    data_hash = hashlib.sha1(data_to_hash.encode()).hexdigest()[:24]

                    builder = InlineKeyboardBuilder()
                    builder.row(
                        InlineKeyboardButton(
                            text="✅ Одобрить",
                            callback_data=f"shorter_name_admin:approve:{data_hash}",
                        ),
                        InlineKeyboardButton(
                            text="❌ Отклонить",
                            callback_data=f"shorter_name_admin:decline:{data_hash}",
                        ),
                    )
                    # Send the message and store its ID for potential future edits
                    sent_message = await bot.send_message(
                        admin_id,
                        notification_text,
                        reply_markup=builder.as_markup(),
                        parse_mode="Markdown",
                    )

                    # --- REFACTOR: Use Redis instead of in-memory cache ---
                    # Store the suggestion context in Redis with a TTL (e.g., 7 days)
                    # This makes the approval/decline buttons stateful across restarts.
                    redis_key = f"suggestion_cache:{data_hash}"
                    payload_to_cache = {
                        "data": data_to_hash,
                        "user_name": offer["user_name"],  # Store the user_name
                        "messages": [{"chat_id": admin_id, "message_id": sent_message.message_id}],
                    }
                    # We use set_cache which handles JSON serialization. TTL is in seconds.
                    await redis_client.set_cache(redis_key, payload_to_cache, ttl=604800)  # 7 days

        except Exception as e:
            logging.error(f"Failed to process pending shorter name offers: {e}", exc_info=True)

        # Send the main summary text
        await message.answer("\n".join(summary_parts), parse_mode="Markdown")

    async def broadcast_release_command(self, message: Message, bot: Bot):
        options, error = self._parse_broadcast_command_args(message.text)
        if error or not options:
            await message.answer(error or BROADCAST_USAGE)
            return

        try:
            broadcast_text, files = load_broadcast_text(options["files"] or None)
            chunks = split_telegram_message(broadcast_text)
        except Exception as exc:
            await message.answer(f"Could not prepare broadcast sources: {exc}")
            return

        if options["user_ids"]:
            target_user_ids = options["user_ids"]
            if options["limit"]:
                target_user_ids = target_user_ids[: options["limit"]]
        else:
            target_user_ids = await database.get_active_broadcast_user_ids(
                options["active_days"],
                include_schedule_subscribers=True,
                limit=options["limit"],
            )

        plan = format_broadcast_plan(
            user_count=len(target_user_ids),
            chunks=chunks,
            files=files,
            active_days=options["active_days"],
            rate_per_second=options["rate"],
            dry_run=not options["execute"],
            include_schedule_subscribers=True,
        )

        if not options["execute"]:
            await message.answer(f"{plan}\n\nDry run only. Add --execute to send.")
            return

        if not target_user_ids:
            await message.answer(f"{plan}\n\nNo target users found.")
            return

        if not chunks:
            await message.answer(f"{plan}\n\nBroadcast text is empty.")
            return

        await message.answer(f"{plan}\n\nSending now.")
        result = await broadcast_chunks_to_users(
            target_user_ids,
            chunks,
            lambda user_id, chunk: self._send_broadcast_message(bot, user_id, chunk),
            rate_per_second=options["rate"],
            dry_run=False,
        )
        await message.answer(format_broadcast_result(result))

    async def set_module_command(self, message: Message):
        """
        Связывает дисциплину с модулем.
        Пример: /set_module Теория игр | Доп. главы математики
        """
        try:
            args = message.text.split(maxsplit=1)[1]
            if "|" not in args:
                raise ValueError

            discipline, module = map(str.strip, args.split("|", 1))

            await database.upsert_discipline_module(discipline, module)
            await message.answer(
                f"✅ Связь создана:\n`{discipline}` -> `{module}`\n\nТеперь эта дисциплина будет считаться частью этого модуля при фильтрации."
            )
        except Exception:
            await message.answer("Ошибка. Формат: `/set_module Дисциплина | Модуль`")

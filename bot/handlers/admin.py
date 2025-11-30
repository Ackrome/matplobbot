from aiogram import  F, Router, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import  Command, Filter
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

import asyncio, json, hashlib
import sys, os, logging
import matplobblib
import pkg_resources
# from main import logging

from shared_lib import database
from .. import keyboards as kb
from shared_lib.redis_client import redis_client
from .. import github_service
from shared_lib.i18n import translator
from ..config import *

import importlib

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
        self.router.message(Command('update'), AdminFilter())(self.update_command)
        self.router.message(Command('clear_cache'), AdminFilter())(self.clear_cache_command)
        self.router.message(Command('send_admin_summary'), AdminFilter())(self.send_admin_summary_command)

    async def _update_library_async(self, library_name: str, lang: str):
        try:
            old_version = pkg_resources.get_distribution(library_name).version
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", "--upgrade", library_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                importlib.reload(pkg_resources)
                new_version = pkg_resources.get_distribution(library_name).version
                return True, translator.gettext(lang, "admin_update_success", library_name=library_name, old_version=old_version, new_version=new_version)
            else:
                error_text = stderr.decode()
                logging.error(f"Error updating library '{library_name}': {error_text}")
                return False, translator.gettext(lang, "admin_update_error", library_name=library_name, error=error_text)
        except Exception as e:
            logging.error(f"Unexpected error during library update: {e}", exc_info=True)
            return False, translator.gettext(lang, "admin_update_unexpected_error", error=e)

    async def update_command(self, message: Message):
        user_id = message.from_user.id
        # --- FIX: replaced get_user_language with get_language ---
        lang = await translator.get_language(user_id) 
        status_msg = await message.answer(translator.gettext(lang, "admin_update_start", library_name='matplobblib'))
        success, status_message_text = await self._update_library_async('matplobblib', lang)
        
        if success:
            importlib.reload(matplobblib)
            await status_msg.edit_text(status_message_text)
        else:
            await status_msg.edit_text(status_message_text)
        
        await message.answer(translator.gettext(lang, "admin_update_finished"), reply_markup=await kb.get_main_reply_keyboard(user_id))

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
        await message.answer(translator.gettext(lang, "admin_clear_cache_finished"), reply_markup=await kb.get_main_reply_keyboard(user_id))

    async def send_admin_summary_command(self, message: Message, bot: Bot, target_chat_id: int | None = None):
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
            async with database.get_db_connection_obj() as db:
                summary_data = await database.get_admin_daily_summary(db)
            summary_parts.append(translator.gettext(lang, "admin_daily_summary_text", **summary_data))
        except Exception as e:
            logging.error(f"Failed to get admin daily summary stats: {e}", exc_info=True)
            summary_parts.append("❌ Не удалось загрузить статистику.")

        # 2. Fetch Pending Shorter Name Offers
        try:
            pending_offers_raw = await redis_client.client.lrange('pending_shorter_offers', 0, -1)
            if pending_offers_raw:                
                summary_parts.append("\n\n" + translator.gettext(lang, "admin_summary_pending_offers_header"))
                
                for offer_raw in pending_offers_raw:
                    offer = json.loads(offer_raw)
                    notification_text = translator.gettext(
                        lang, "shorter_name_admin_notification",
                        user_id=offer['user_id'], user_name=offer['user_name'],
                        full_name=offer['full_name'], short_name=offer['short_name']
                    )
                    
                    data_to_hash = f"{offer['user_id']}:{offer['full_name']}:{offer['short_name']}"
                    data_hash = hashlib.sha1(data_to_hash.encode()).hexdigest()[:24]
                    
                    builder = InlineKeyboardBuilder()
                    builder.row(
                        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"shorter_name_admin:approve:{data_hash}"),
                        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"shorter_name_admin:decline:{data_hash}")
                    )
                    # Send the message and store its ID for potential future edits
                    sent_message = await bot.send_message(admin_id, notification_text, reply_markup=builder.as_markup(), parse_mode='Markdown')

                    # --- REFACTOR: Use Redis instead of in-memory cache ---
                    # Store the suggestion context in Redis with a TTL (e.g., 7 days)
                    # This makes the approval/decline buttons stateful across restarts.
                    redis_key = f"suggestion_cache:{data_hash}"
                    payload_to_cache = {
                        'data': data_to_hash,
                        'user_name': offer['user_name'], # Store the user_name
                        'messages': [{'chat_id': admin_id, 'message_id': sent_message.message_id}]
                    }
                    # We use set_cache which handles JSON serialization. TTL is in seconds.
                    await redis_client.set_cache(redis_key, payload_to_cache, ttl=604800) # 7 days

        except Exception as e:
            logging.error(f"Failed to process pending shorter name offers: {e}", exc_info=True)

        # Send the main summary text
        await message.answer("\n".join(summary_parts), parse_mode="Markdown")
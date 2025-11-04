from aiogram import  F, Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import  Command, Filter
import asyncio
import sys, os, logging
import matplobblib
import pkg_resources
# from main import logging

from .. import database
from .. import keyboards as kb
from shared_lib.redis_client import redis_client
from .. import github_service
from shared_lib.i18n import translator
from ..config import *

import importlib

class AdminFilter(Filter):
    """A filter to check if the user is the administrator."""
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user_id = event.from_user.id
        if user_id == ADMIN_USER_ID:
            return True
        
        # If not an admin, send a permission denied message and stop processing.
        lang = await translator.get_user_language(user_id)
        text = translator.gettext(lang, "admin_no_permission")
        
        if isinstance(event, Message):
            await event.reply(text, reply_markup=await kb.get_main_reply_keyboard(user_id))
        elif isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
            
        return False

class AdminManager:
    def __init__(self):
        self.router = Router()
        # Apply the AdminFilter to all handlers in this router
        self.router.message.filter(AdminFilter())
        self.router.callback_query.filter(AdminFilter())
        self._register_handlers()

    def _register_handlers(self):
        self.router.message(Command('update'))(self.update_command)
        self.router.message(Command('clear_cache'))(self.clear_cache_command)

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
        lang = await translator.get_user_language(user_id)
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
        lang = await translator.get_user_language(user_id)
        status_msg = await message.answer(translator.gettext(lang, "admin_clear_cache_start"))

        await redis_client.clear_all_user_cache()
        kb.code_path_cache.clear()
        github_service.github_content_cache.clear()
        github_service.github_dir_cache.clear()
        await database.clear_latex_cache()

        await status_msg.edit_text(translator.gettext(lang, "admin_clear_cache_success"))
        await message.answer(translator.gettext(lang, "admin_clear_cache_finished"), reply_markup=await kb.get_main_reply_keyboard(user_id))
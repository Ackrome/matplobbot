from aiogram import  F, Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import  Command

import asyncio
import sys
import matplotlib
matplotlib.use('Agg') # Use a non-interactive backend for server environments
import matplobblib
import os
import pkg_resources
# from main import logging

from .. import database
from .. import keyboards as kb
from ..redis_client import redis_client
from .. import github_service
from shared_lib.i18n import translator
from ..config import *

import importlib

router = Router()


async def update_library_async(library_name: str, lang: str):
    try:
        # 1. Get the version before updating
        old_version = pkg_resources.get_distribution(library_name).version

        process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "pip", "install", "--upgrade", library_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            # 2. Reload the package metadata to get the new version
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

##################################################################################################
# UPDATE
##################################################################################################


@router.message(Command('update'))
async def update(message: Message):
    user_id = message.from_user.id
    lang = await translator.get_user_language(user_id)
    if user_id != ADMIN_USER_ID:
        await message.reply(translator.gettext(lang, "admin_no_permission"), reply_markup=await kb.get_main_reply_keyboard(user_id))
        return

    status_msg = await message.answer(translator.gettext(lang, "admin_update_start", library_name='matplobblib'))
    # You can add:
    # await message.answer_chat_action("typing")
    success, status_message_text = await update_library_async('matplobblib', lang)
    if success:
        # Перезагрузка модуля matplobblib, если это необходимо для немедленного применения изменений
        importlib.reload(matplobblib) # Может быть сложным и иметь побочные эффекты
        await status_msg.edit_text(status_message_text) # Убран reply_markup
    else:
        await status_msg.edit_text(status_message_text) # Убран reply_markup
    
    await message.answer(translator.gettext(lang, "admin_update_finished"), reply_markup=await kb.get_main_reply_keyboard(user_id))
##################################################################################################
# CLEAR CACHE
##################################################################################################
@router.message(Command('clear_cache'))
async def clear_cache_command(message: Message):
    """Handles the /clear_cache command, admin-only. Clears all application caches."""
    user_id = message.from_user.id
    lang = await translator.get_user_language(user_id)
    if user_id != ADMIN_USER_ID:
        await message.reply(translator.gettext(lang, "admin_no_permission"), reply_markup=await kb.get_main_reply_keyboard(user_id))
        return

    status_msg = await message.answer(translator.gettext(lang, "admin_clear_cache_start"))

    # 1. Clear Redis user caches
    await redis_client.clear_all_user_cache()
    
    # 2. Clear in-memory caches from other modules
    kb.code_path_cache.clear()
    # github_search_cache is a TTLCache and will expire on its own
    github_service.github_content_cache.clear()
    github_service.github_dir_cache.clear()

    # 3. Clear persistent cache in database
    await database.clear_latex_cache()

    await status_msg.edit_text(translator.gettext(lang, "admin_clear_cache_success"))
    await message.answer(translator.gettext(lang, "admin_clear_cache_finished"), reply_markup=await kb.get_main_reply_keyboard(user_id))


@router.callback_query(F.data == "help_cmd_update")
async def cq_help_cmd_update(callback: CallbackQuery):
    """Handler for '/update' button from help menu."""
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    if user_id != ADMIN_USER_ID:
        await callback.answer(translator.gettext(lang, "admin_no_permission"), show_alert=True)
        return

    await callback.answer(translator.gettext(lang, "admin_update_starting_callback"))
    
    # Повторяем логику команды /update
    status_msg = await callback.message.answer(translator.gettext(lang, "admin_update_start", library_name='matplobblib'))
    success, status_message_text = await update_library_async('matplobblib', lang)
    if success:
        import importlib
        importlib.reload(matplobblib)
        await status_msg.edit_text(status_message_text)
    else:
        await status_msg.edit_text(status_message_text)
    await callback.message.answer(translator.gettext(lang, "admin_update_finished"), reply_markup=await kb.get_main_reply_keyboard(user_id))

@router.callback_query(F.data == "help_cmd_clear_cache")
async def cq_help_cmd_clear_cache(callback: CallbackQuery):
    """Handler for '/clear_cache' button from help menu."""
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    if user_id != ADMIN_USER_ID:
        await callback.answer(translator.gettext(lang, "admin_no_permission"), show_alert=True)
        return

    await callback.answer(translator.gettext(lang, "admin_clear_cache_start"))
    
    # Повторяем логику команды /clear_cache
    # clear_cache_command ожидает объект Message, callback.message подходит
    await clear_cache_command(callback.message)
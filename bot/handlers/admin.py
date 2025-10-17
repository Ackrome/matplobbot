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
from ..config import *

import importlib

router = Router()


async def update_library_async(library_name):
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
            return True, f"Библиотека '{library_name}' успешно обновлена с {old_version} до {new_version}!"
        else:
            print(f"Ошибка при обновлении библиотеки '{library_name}': {stderr.decode()}")
            return False, f"Ошибка при обновлении библиотеки '{library_name}': {stderr.decode()}"
    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")
        return False, f"Произошла непредвиденная ошибка: {e}"

##################################################################################################
# UPDATE
##################################################################################################


@router.message(Command('update'))
async def update(message: Message):
    if message.from_user.id != ADMIN_USER_ID:
        await message.reply("У вас нет прав на использование этой команды.", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))
        return

    status_msg = await message.answer("Начинаю обновление библиотеки `matplobblib`...")
    # Можно добавить 
    # await message.answer_chat_action("typing")
    success, status_message_text = await update_library_async('matplobblib')
    if success:
        # Перезагрузка модуля matplobblib, если это необходимо для немедленного применения изменений
        importlib.reload(matplobblib) # Может быть сложным и иметь побочные эффекты
        await status_msg.edit_text(status_message_text) # Убран reply_markup
    else:
        await status_msg.edit_text(status_message_text) # Убран reply_markup
    
    await message.answer("Обновление завершено. Выберите следующую команду:", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))
##################################################################################################
# CLEAR CACHE
##################################################################################################
@router.message(Command('clear_cache'))
async def clear_cache_command(message: Message):
    """Handles the /clear_cache command, admin-only. Clears all application caches."""
    if message.from_user.id != ADMIN_USER_ID:
        await message.reply("У вас нет прав на использование этой команды.", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))
        return

    status_msg = await message.answer("Начинаю очистку кэша...")

    # 1. Clear Redis user caches
    await redis_client.clear_all_user_cache()
    
    # 2. Clear in-memory caches from other modules
    kb.code_path_cache.clear()
    # github_search_cache is a TTLCache and will expire on its own
    github_service.github_content_cache.clear()
    github_service.github_dir_cache.clear()

    # 3. Clear persistent cache in database
    await database.clear_latex_cache()

    await status_msg.edit_text("✅ Весь кэш приложения был успешно очищен.")
    await message.answer("Выберите следующую команду:", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))


@router.callback_query(F.data == "help_cmd_update")
async def cq_help_cmd_update(callback: CallbackQuery):
    """Handler for '/update' button from help menu."""
    if callback.from_user.id != ADMIN_USER_ID:
        await callback.answer("У вас нет прав на использование этой команды.", show_alert=True)
        return

    await callback.answer("Начинаю обновление...")
    
    # Повторяем логику команды /update
    status_msg = await callback.message.answer("Начинаю обновление библиотеки `matplobblib`...")
    success, status_message_text = await update_library_async('matplobblib')
    if success:
        import importlib
        importlib.reload(matplobblib)
        await status_msg.edit_text(status_message_text)
    else:
        await status_msg.edit_text(status_message_text)
    await callback.message.answer("Обновление завершено. Выберите следующую команду:", reply_markup=kb.get_main_reply_keyboard(callback.from_user.id))

@router.callback_query(F.data == "help_cmd_clear_cache")
async def cq_help_cmd_clear_cache(callback: CallbackQuery):
    """Handler for '/clear_cache' button from help menu."""
    if callback.from_user.id != ADMIN_USER_ID:
        await callback.answer("У вас нет прав на использование этой команды.", show_alert=True)
        return

    await callback.answer("Начинаю очистку кэша...")
    
    # Повторяем логику команды /clear_cache
    # clear_cache_command ожидает объект Message, callback.message подходит
    await clear_cache_command(callback.message)
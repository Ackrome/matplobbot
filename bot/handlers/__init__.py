from aiogram import Router

from . import base, library, github, rendering, admin
from .settings import settings_router
from .schedule import ScheduleManager

# Создаем главный роутер для всего модуля handlers
router = Router()

def setup_handlers(dp: Router, ruz_api_client):
    """Function to setup all handlers"""
    schedule_manager = ScheduleManager(ruz_api_client)

    dp.include_router(base.router)
    dp.include_router(library.router)
    dp.include_router(github.router)
    dp.include_router(rendering.router)
    dp.include_router(settings_router)
    dp.include_router(admin.router)
    dp.include_router(schedule_manager.router)
from aiogram import Router

from . import base, library, github, rendering, settings, admin, schedule

# Создаем главный роутер для всего модуля handlers
router = Router()

# Включаем в него все остальные роутеры
router.include_router(base.router)
router.include_router(library.router)
router.include_router(github.router)
router.include_router(rendering.router)
router.include_router(settings.router)
router.include_router(admin.router)
router.include_router(schedule.router)
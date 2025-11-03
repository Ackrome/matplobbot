from aiogram import Router

from . import main, display, language, latex, subscriptions

settings_router = Router()

settings_router.include_router(main.router)
settings_router.include_router(display.router)
settings_router.include_router(language.router)
settings_router.include_router(latex.router)
settings_router.include_router(subscriptions.router)
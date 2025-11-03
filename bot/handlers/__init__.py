from aiogram import Router

from .schedule import ScheduleManager
from .github import GitHubManager
from .library import LibraryManager
from .admin import AdminManager
from .rendering import RenderingManager
from .base import BaseManager
from .settings import SettingsManager

# Создаем главный роутер для всего модуля handlers
router = Router()

def setup_handlers(dp: Router, ruz_api_client):
    """Function to setup all handlers"""
    # Instantiate all specialized managers first
    schedule_manager = ScheduleManager(ruz_api_client)
    github_manager = GitHubManager()
    library_manager = LibraryManager()
    admin_manager = AdminManager()
    rendering_manager = RenderingManager()
    settings_manager = SettingsManager(schedule_manager) # Inject dependency
    # Instantiate the base manager, injecting other managers as dependencies
    base_manager = BaseManager(library_manager, github_manager, schedule_manager, rendering_manager, admin_manager, settings_manager) # No change needed here

    # Include all routers. The order can matter for overlapping filters, so base/onboarding goes first.
    dp.include_router(base_manager.router)
    dp.include_router(library_manager.router)
    dp.include_router(github_manager.router)
    dp.include_router(rendering_manager.router)
    dp.include_router(admin_manager.router)
    dp.include_router(schedule_manager.router)
    dp.include_router(settings_manager.router)
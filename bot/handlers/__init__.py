from aiogram import Router

from .schedule import ScheduleManager
from .github import GitHubManager
from .library import LibraryManager
from .admin import AdminManager
from .rendering import RenderingManager
from .base import BaseManager
from .suggestions import SuggestionsManager
from .settings import SettingsManager

# Создаем главный роутер для всего модуля handlers
router = Router()

def setup_handlers(dp: Router, bot, ruz_api_client):
    """Function to setup all handlers"""
    # Instantiate all specialized managers first
    github_manager = GitHubManager()
    library_manager = LibraryManager()
    admin_manager = AdminManager()
    rendering_manager = RenderingManager()
    schedule_manager = ScheduleManager(ruz_api_client) # schedule_manager doesn't depend on base/settings
    suggestions_manager = SuggestionsManager(bot)

    settings_manager = SettingsManager(schedule_manager, admin_manager) # Instantiate SettingsManager first, passing schedule_manager
    
    # --- ВАЖНОЕ ИЗМЕНЕНИЕ: передаем suggestions_manager последним аргументом ---
    base_manager = BaseManager(library_manager, github_manager, schedule_manager, rendering_manager, admin_manager, settings_manager, suggestions_manager)
    
    settings_manager.set_base_manager(base_manager) # Inject base_manager into settings_manager

    # Include all routers. The order can matter for overlapping filters, so base/onboarding goes first.
    dp.include_router(base_manager.router)
    dp.include_router(library_manager.router)
    dp.include_router(github_manager.router)
    dp.include_router(rendering_manager.router)
    dp.include_router(admin_manager.router)
    dp.include_router(schedule_manager.router)
    dp.include_router(suggestions_manager.router)
    dp.include_router(settings_manager.router)
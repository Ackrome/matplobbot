import asyncpg
import datetime
import logging
import json
import os

logger = logging.getLogger(__name__)

# This file is part of the bot-specific application logic.
# However, database connections are now handled by the shared_lib.
# This file might be used for bot-specific DB functions in the future,
# but for connection pooling, we rely on the shared module.
# To prevent conflicts, we will ensure this file does not attempt to create its own pool.
from shared_lib.database import (init_db_pool, get_user_settings, update_user_settings_db, add_favorite,
                                  remove_favorite, get_favorites, clear_latex_cache, add_user_repo, get_user_repos,
                                  remove_user_repo, update_user_repo, is_onboarding_completed, set_onboarding_completed,
                                  add_schedule_subscription, get_subscriptions_for_notification, log_user_action,
                                  get_user_subscriptions, update_subscription_hash)

# --- User Settings Defaults ---
# Эти настройки используются по умолчанию, если для пользователя нет записи в БД
# или если конкретная настройка отсутствует в его записи.
DEFAULT_SETTINGS = {
    'show_docstring': True,
    'latex_padding': 15,
    'md_display_mode': 'md_file',
    'latex_dpi': 300,
    'language': 'en',
}
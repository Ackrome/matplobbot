import logging

from shared_lib.database import (
    add_favorite as add_favorite,
    add_schedule_subscription as add_schedule_subscription,
    add_user_repo as add_user_repo,
    clear_latex_cache as clear_latex_cache,
    get_admin_daily_summary as get_admin_daily_summary,
    get_favorites as get_favorites,
    get_or_create_calendar_secret as get_or_create_calendar_secret,
    get_session as get_session,
    get_subscription_by_id as get_subscription_by_id,
    get_subscriptions_for_notification as get_subscriptions_for_notification,
    get_user_repos as get_user_repos,
    get_user_settings as get_user_settings,
    get_user_subscriptions as get_user_subscriptions,
    init_db_pool as init_db_pool,
    is_onboarding_completed as is_onboarding_completed,
    log_user_action as log_user_action,
    regenerate_calendar_secret as regenerate_calendar_secret,
    remove_favorite as remove_favorite,
    remove_user_repo as remove_user_repo,
    set_onboarding_completed as set_onboarding_completed,
    update_subscription_hash as update_subscription_hash,
    update_user_repo as update_user_repo,
    update_user_settings_db as update_user_settings_db,
    upsert_discipline_module as upsert_discipline_module,
)

logger = logging.getLogger(__name__)

# Backward-compatible facade for bot modules that still import `bot.database`.
# Actual DB implementation lives in `shared_lib.database`.
DEFAULT_SETTINGS = {
    "show_docstring": True,
    "latex_padding": 15,
    "md_display_mode": "md_file",
    "latex_dpi": 300,
    "language": "en",
}

__all__ = [
    "DEFAULT_SETTINGS",
    "init_db_pool",
    "get_user_settings",
    "update_user_settings_db",
    "add_favorite",
    "remove_favorite",
    "get_favorites",
    "clear_latex_cache",
    "add_user_repo",
    "get_user_repos",
    "remove_user_repo",
    "update_user_repo",
    "is_onboarding_completed",
    "set_onboarding_completed",
    "add_schedule_subscription",
    "get_subscriptions_for_notification",
    "log_user_action",
    "get_user_subscriptions",
    "update_subscription_hash",
    "get_or_create_calendar_secret",
    "regenerate_calendar_secret",
    "get_subscription_by_id",
    "get_session",
    "get_admin_daily_summary",
    "upsert_discipline_module",
]

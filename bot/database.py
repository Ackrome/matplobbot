import logging

from shared_lib.database import (
    add_favorite as add_favorite,
)
from shared_lib.database import (
    add_schedule_subscription as add_schedule_subscription,
)
from shared_lib.database import (
    add_user_repo as add_user_repo,
)
from shared_lib.database import (
    clear_latex_cache as clear_latex_cache,
)
from shared_lib.database import (
    delete_user_myschedule_filter_preset as delete_user_myschedule_filter_preset,
)
from shared_lib.database import (
    delete_user_search_preset as delete_user_search_preset,
)
from shared_lib.database import (
    get_admin_daily_summary as get_admin_daily_summary,
)
from shared_lib.database import (
    get_favorites as get_favorites,
)
from shared_lib.database import (
    get_or_create_calendar_secret as get_or_create_calendar_secret,
)
from shared_lib.database import (
    get_or_create_web_account_preferences_for_telegram as get_or_create_web_account_preferences_for_telegram,
)
from shared_lib.database import (
    get_session as get_session,
)
from shared_lib.database import (
    get_subscription_by_id as get_subscription_by_id,
)
from shared_lib.database import (
    get_subscriptions_for_notification as get_subscriptions_for_notification,
)
from shared_lib.database import (
    get_user_myschedule_filter_preset as get_user_myschedule_filter_preset,
)
from shared_lib.database import (
    get_user_myschedule_filter_presets as get_user_myschedule_filter_presets,
)
from shared_lib.database import (
    get_user_myschedule_filters as get_user_myschedule_filters,
)
from shared_lib.database import (
    get_user_repos as get_user_repos,
)
from shared_lib.database import (
    get_user_search_preset as get_user_search_preset,
)
from shared_lib.database import (
    get_user_search_presets as get_user_search_presets,
)
from shared_lib.database import (
    get_user_settings as get_user_settings,
)
from shared_lib.database import (
    get_user_subscriptions as get_user_subscriptions,
)
from shared_lib.database import (
    init_db_pool as init_db_pool,
)
from shared_lib.database import (
    is_onboarding_completed as is_onboarding_completed,
)
from shared_lib.database import (
    log_user_action as log_user_action,
)
from shared_lib.database import (
    regenerate_calendar_secret as regenerate_calendar_secret,
)
from shared_lib.database import (
    remove_favorite as remove_favorite,
)
from shared_lib.database import (
    remove_user_repo as remove_user_repo,
)
from shared_lib.database import (
    save_user_myschedule_filter_preset as save_user_myschedule_filter_preset,
)
from shared_lib.database import (
    save_user_myschedule_filters as save_user_myschedule_filters,
)
from shared_lib.database import (
    save_user_search_preset as save_user_search_preset,
)
from shared_lib.database import (
    save_web_account_preferences_for_telegram as save_web_account_preferences_for_telegram,
)
from shared_lib.database import (
    set_onboarding_completed as set_onboarding_completed,
)
from shared_lib.database import (
    update_subscription_hash as update_subscription_hash,
)
from shared_lib.database import (
    update_user_repo as update_user_repo,
)
from shared_lib.database import (
    update_user_settings_db as update_user_settings_db,
)
from shared_lib.database import (
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
    "search_presets": [],
    "myschedule_filters": {"excluded_subs": [], "excluded_types": []},
    "myschedule_filter_presets": [],
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
    "get_or_create_web_account_preferences_for_telegram",
    "regenerate_calendar_secret",
    "save_web_account_preferences_for_telegram",
    "get_subscription_by_id",
    "get_session",
    "get_admin_daily_summary",
    "upsert_discipline_module",
    "get_user_search_presets",
    "get_user_search_preset",
    "save_user_search_preset",
    "delete_user_search_preset",
    "get_user_myschedule_filters",
    "save_user_myschedule_filters",
    "get_user_myschedule_filter_presets",
    "get_user_myschedule_filter_preset",
    "save_user_myschedule_filter_preset",
    "delete_user_myschedule_filter_preset",
]

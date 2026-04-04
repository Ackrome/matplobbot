import logging

logger = logging.getLogger(__name__)

# This file is part of the bot-specific application logic.
# However, database connections are now handled by the shared_lib.
# This file might be used for bot-specific DB functions in the future,
# but for connection pooling, we rely on the shared module.
# To prevent conflicts, we will ensure this file does not attempt to create its own pool.

# --- User Settings Defaults ---
# Эти настройки используются по умолчанию, если для пользователя нет записи в БД
# или если конкретная настройка отсутствует в его записи.
DEFAULT_SETTINGS = {
    "show_docstring": True,
    "latex_padding": 15,
    "md_display_mode": "md_file",
    "latex_dpi": 300,
    "language": "en",
}

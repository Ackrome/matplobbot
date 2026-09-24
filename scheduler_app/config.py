import logging
import os

from shared_lib.egress import get_telegram_proxy_url

# --- Telegram Configuration ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_PROXY_URL = get_telegram_proxy_url()


def _read_non_negative_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _read_non_negative_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


TELEGRAM_REQUEST_RETRY_ATTEMPTS = _read_non_negative_int("TELEGRAM_REQUEST_RETRY_ATTEMPTS", 1)
TELEGRAM_REQUEST_RETRY_DELAY_SECONDS = _read_non_negative_float(
    "TELEGRAM_REQUEST_RETRY_DELAY_SECONDS", 0.5
)
SCHEDULE_OUTBOX_MAX_ATTEMPTS = max(
    1,
    _read_non_negative_int("SCHEDULE_OUTBOX_MAX_ATTEMPTS", 8),
)
SCHEDULE_OUTBOX_BASE_DELAY_SECONDS = _read_non_negative_float(
    "SCHEDULE_OUTBOX_BASE_DELAY_SECONDS", 60.0
)
CELERY_QUEUE_ALERT_THRESHOLD = max(
    1,
    _read_non_negative_int("CELERY_QUEUE_ALERT_THRESHOLD", 100),
)

# --- PostgreSQL Database Configuration ---
# The DATABASE_URL is now the single source of truth, read from the environment.
DATABASE_URL = os.getenv("DATABASE_URL")

admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
if not admin_ids_str:
    logging.warning(
        "ADMIN_USER_IDS environment variable is not set. Admin commands will be disabled."
    )
    ADMIN_USER_IDS = []
else:
    ADMIN_USER_IDS = [
        int(admin_id.strip()) for admin_id in admin_ids_str.split(",") if admin_id.strip().isdigit()
    ]

import os

# --- PostgreSQL Database Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL")

# --- Logging Configuration ---
LOG_DIR = "/app/logs"
BOT_LOG_FILE_NAME = "bot.log"
FASTAPI_LOG_FILE_NAME = "fastapi_app.log"

# --- Admin Panel Auth ---
STATS_USER = os.getenv("STATS_USER", "admin")
STATS_PASS = os.getenv("STATS_PASS", "admin")


def _parse_admin_user_ids() -> set[int]:
    raw_ids = os.getenv("ADMIN_USER_IDS", "")
    if not raw_ids:
        return set()

    parsed_ids: set[int] = set()
    for raw_id in raw_ids.split(","):
        raw_id = raw_id.strip()
        if raw_id.isdigit():
            parsed_ids.add(int(raw_id))
    return parsed_ids


ADMIN_USER_IDS = _parse_admin_user_ids()
PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "").rstrip("/")

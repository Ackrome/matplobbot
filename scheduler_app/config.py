import os

# --- Telegram Configuration ---
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- PostgreSQL Database Configuration ---
# The DATABASE_URL is now the single source of truth, read from the environment.
DATABASE_URL = os.getenv("DATABASE_URL")

LOG_DIR = "/app/logs"
SCHEDULER_LOG_FILE = "scheduler.log"

admin_ids_str = os.getenv('ADMIN_USER_IDS', '')
if not admin_ids_str:
    logging.warning("ADMIN_USER_IDS environment variable is not set. Admin commands will be disabled.")
    ADMIN_USER_IDS = []
else:
    ADMIN_USER_IDS = [int(admin_id.strip()) for admin_id in admin_ids_str.split(',') if admin_id.strip().isdigit()]
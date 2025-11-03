import os

# --- Telegram Configuration ---
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- PostgreSQL Database Configuration ---
# The DATABASE_URL is now the single source of truth, read from the environment.
DATABASE_URL = os.getenv("DATABASE_URL")

LOG_DIR = "/app/logs"
SCHEDULER_LOG_FILE = "scheduler.log"
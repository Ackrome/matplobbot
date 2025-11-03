import os

# --- PostgreSQL Database Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL") # This is correct, but was being overridden elsewhere.

# --- Logging Configuration ---
LOG_DIR = "/app/logs"
BOT_LOG_FILE_NAME = "bot.log" # Имя файла логов бота
FASTAPI_LOG_FILE_NAME = "fastapi_app.log" # Имя файла логов FastAPI
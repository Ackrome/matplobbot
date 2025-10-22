import os

# --- PostgreSQL Database Configuration ---
POSTGRES_USER = os.getenv("POSTGRES_USER", "user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "matplobbot_db")

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# --- Logging Configuration ---
LOG_DIR = "/app/logs"
BOT_LOG_FILE_NAME = "bot.log" # Имя файла логов бота
FASTAPI_LOG_FILE_NAME = "fastapi_app.log" # Имя файла логов FastAPI
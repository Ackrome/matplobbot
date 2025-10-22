import asyncpg
import datetime
import logging
import json
import os

logger = logging.getLogger(__name__)

# --- PostgreSQL Database Configuration ---
POSTGRES_USER = os.getenv("POSTGRES_USER", "user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "matplobbot_db")

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Global connection pool
pool = None

async def init_db_pool():
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=5, max_size=20)
        logger.info("Bot: Database connection pool created successfully.")

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

async def init_db():
    """Initializes the database and creates tables if they don't exist."""
    if pool is None:
        await init_db_pool()
        
    async with pool.acquire() as connection:
        async with connection.transaction():
            # Note: PostgreSQL syntax is used here.
            # SERIAL is auto-incrementing integer.
            # TIMESTAMPTZ is timestamp with time zone.
            await connection.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                full_name TEXT NOT NULL,
                avatar_pic_url TEXT,
                settings JSONB DEFAULT '{}'::jsonb,
                onboarding_completed BOOLEAN DEFAULT FALSE
            )
            ''')
            await connection.execute('''
            CREATE TABLE IF NOT EXISTS user_actions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                action_type TEXT NOT NULL,
                action_details TEXT,
                timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            await connection.execute('''
            CREATE TABLE IF NOT EXISTS user_favorites (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                code_path TEXT NOT NULL, -- e.g., "pyplot.line_plot.simple_plot"
                added_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, code_path)
            )
            ''')
            await connection.execute('''
            CREATE TABLE IF NOT EXISTS latex_cache (
                formula_hash TEXT PRIMARY KEY,
                image_url TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            await connection.execute('''
            CREATE TABLE IF NOT EXISTS user_github_repos (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                repo_path TEXT NOT NULL, -- e.g., "owner/repo"
                added_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, repo_path)
            )
            ''')
    logger.info("Database tables initialized.")

async def log_user_action(user_id: int, username: str | None, full_name: str, avatar_pic_url: str | None, action_type: str, action_details: str | None):
    """Записывает информацию о пользователе и его действие в базу данных."""
    async with pool.acquire() as connection:
        try:
            # Upsert user information
            await connection.execute('''
                INSERT INTO users (user_id, username, full_name, avatar_pic_url)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    full_name = EXCLUDED.full_name,
                    avatar_pic_url = EXCLUDED.avatar_pic_url;
            ''', user_id, username, full_name, avatar_pic_url)

            # Log the action
            await connection.execute('''
                INSERT INTO user_actions (user_id, action_type, action_details, timestamp)
                VALUES ($1, $2, $3, $4);
            ''', user_id, action_type, action_details, datetime.datetime.now())
        except Exception as e:
            logger.error(f"Ошибка при записи действия пользователя в БД: {e}", exc_info=True)

async def get_user_settings_db(user_id: int) -> dict:
    """
    Получает настройки пользователя из БД.
    Возвращает пустой словарь, если пользователь не найден или настройки отсутствуют/некорректны.
    """
    async with pool.acquire() as connection:
        settings_json = await connection.fetchval("SELECT settings FROM users WHERE user_id = $1", user_id)
        if settings_json:
            try:
                return json.loads(settings_json)
            except json.JSONDecodeError:
                logger.error(f"Error decoding JSON settings for user {user_id}: {settings_json}")
                return {}
        return {}

async def get_user_settings(user_id: int) -> dict:
    """Получает настройки для пользователя из БД, объединяя их с настройками по умолчанию."""
    db_settings = await get_user_settings_db(user_id)
    merged_settings = DEFAULT_SETTINGS.copy()
    merged_settings.update(db_settings) # Настройки из БД переопределяют дефолтные
    return merged_settings


async def update_user_settings_db(user_id: int, settings: dict):
    """
    Обновляет настройки пользователя в БД.
    """
    async with pool.acquire() as connection:
        settings_json = json.dumps(settings)
        await connection.execute("UPDATE users SET settings = $1 WHERE user_id = $2", settings_json, user_id)

async def add_favorite(user_id: int, code_path: str):
    """Добавляет пример кода в избранное."""
    async with pool.acquire() as connection:
        try:
            await connection.execute("INSERT INTO user_favorites (user_id, code_path) VALUES ($1, $2)", user_id, code_path)
            return True
        except asyncpg.UniqueViolationError:
            logger.warning(f"Попытка повторно добавить в избранное: user {user_id}, path {code_path}")
            return False # Уже существует

async def remove_favorite(user_id: int, code_path: str):
    """Удаляет пример кода из избранного."""
    async with pool.acquire() as connection:
        await connection.execute("DELETE FROM user_favorites WHERE user_id = $1 AND code_path = $2", user_id, code_path)

async def get_favorites(user_id: int) -> list:
    """Получает список избранных примеров кода для пользователя."""
    async with pool.acquire() as connection:
        rows = await connection.fetch("SELECT code_path FROM user_favorites WHERE user_id = $1 ORDER BY added_at DESC", user_id)
        return [row['code_path'] for row in rows]


async def clear_latex_cache():
    """Clears all entries from the latex_cache table."""
    async with pool.acquire() as connection:
        await connection.execute("TRUNCATE TABLE latex_cache")
        logger.info("LaTeX cache table has been cleared.")

# --- GitHub Repos ---

async def add_user_repo(user_id: int, repo_path: str) -> bool:
    """Adds a GitHub repository to the user's list."""
    async with pool.acquire() as connection:
        try:
            await connection.execute("INSERT INTO user_github_repos (user_id, repo_path) VALUES ($1, $2)", user_id, repo_path)
            logger.info(f"User {user_id} added repo {repo_path}")
            return True
        except asyncpg.UniqueViolationError:
            logger.warning(f"Attempt to re-add repo for user {user_id}: {repo_path}")
            return False # Already exists

async def get_user_repos(user_id: int) -> list[str]:
    """Gets the list of GitHub repositories for a user."""
    async with pool.acquire() as connection:
        rows = await connection.fetch("SELECT repo_path FROM user_github_repos WHERE user_id = $1 ORDER BY added_at ASC", user_id)
        return [row['repo_path'] for row in rows]

async def remove_user_repo(user_id: int, repo_path: str) -> bool:
    """Removes a GitHub repository from the user's list."""
    async with pool.acquire() as connection:
        result = await connection.execute("DELETE FROM user_github_repos WHERE user_id = $1 AND repo_path = $2", user_id, repo_path)
        deleted_rows = int(result.split(' ')[-1]) > 0
        if deleted_rows:
            logger.info(f"User {user_id} removed repo {repo_path}")
        return deleted_rows

async def update_user_repo(user_id: int, old_repo_path: str, new_repo_path: str):
    """Updates a user's repository path."""
    async with pool.acquire() as connection:
        await connection.execute("UPDATE user_github_repos SET repo_path = $1 WHERE user_id = $2 AND repo_path = $3", new_repo_path, user_id, old_repo_path)
        logger.info(f"User {user_id} updated repo from {old_repo_path} to {new_repo_path}")

# --- Onboarding ---

async def is_onboarding_completed(user_id: int) -> bool:
    """Checks if the user has completed the onboarding process."""
    async with pool.acquire() as connection:
        completed = await connection.fetchval("SELECT onboarding_completed FROM users WHERE user_id = $1", user_id)
        return completed or False

async def set_onboarding_completed(user_id: int):
    """Marks the onboarding process as completed for a user."""
    async with pool.acquire() as connection:
        await connection.execute("UPDATE users SET onboarding_completed = TRUE WHERE user_id = $1", user_id)
        logger.info(f"Onboarding marked as completed for user {user_id}")
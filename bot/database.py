import aiosqlite
import datetime
import logging
import json
import os

DB_DIR = "/app/db_data"  # Путь внутри контейнера, где будет храниться БД
DB_NAME = os.path.join(DB_DIR, "user_actions.db")

logger = logging.getLogger(__name__)

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
    """Инициализирует базу данных и создает таблицу, если она не существует."""
    try:
        os.makedirs(DB_DIR, exist_ok=True)
        logger.info(f"Директория для БД {DB_DIR} проверена/создана.")
    except OSError as e:
        logger.error(f"Не удалось создать директорию {DB_DIR}: {e}")
        raise  # Прерываем выполнение, если не можем создать директорию

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("PRAGMA foreign_keys = ON;")
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT NOT NULL,
                avatar_pic_url TEXT,
                settings TEXT DEFAULT '{}', -- Новое поле для хранения настроек в JSON
                onboarding_completed BOOLEAN DEFAULT FALSE
            )
        ''')
        # Проверяем, существует ли столбец 'settings' (для обновления существующих БД)
        cursor = await db.execute("PRAGMA table_info(users);")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        if 'settings' not in column_names:
            await db.execute("ALTER TABLE users ADD COLUMN settings TEXT DEFAULT '{}';")
            logger.info("Добавлен столбец 'settings' в таблицу 'users'.")
        if 'onboarding_completed' not in column_names:
            await db.execute("ALTER TABLE users ADD COLUMN onboarding_completed BOOLEAN DEFAULT FALSE;")
            logger.info("Добавлен столбец 'onboarding_completed' в таблицу 'users'.")
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                action_details TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                code_path TEXT NOT NULL, -- e.g., "pyplot.line_plot.simple_plot"
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                UNIQUE(user_id, code_path)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS latex_cache (
                formula_hash TEXT PRIMARY KEY,
                image_url TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_github_repos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                repo_path TEXT NOT NULL, -- e.g., "owner/repo"
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                UNIQUE(user_id, repo_path)
            )
        ''')
        await db.commit()
    logger.info(f"База данных {DB_NAME} инициализирована.")

async def log_user_action(user_id: int, username: str | None, full_name: str, avatar_pic_url: str | None, action_type: str, action_details: str | None):
    """Записывает информацию о пользователе и его действие в базу данных."""
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            await db.execute("PRAGMA foreign_keys = ON;")
            # Добавляем или обновляем информацию о пользователе
            await db.execute('''
                INSERT INTO users (user_id, username, full_name, avatar_pic_url)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    full_name = excluded.full_name,
                    avatar_pic_url = excluded.avatar_pic_url
            ''', (user_id, username, full_name, avatar_pic_url))

            # Записываем действие пользователя
            await db.execute('''
                INSERT INTO user_actions (user_id, action_type, action_details, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (user_id, action_type, action_details, datetime.datetime.now()))
            await db.commit()
        except Exception as e:
            logger.error(f"Ошибка при записи действия пользователя в БД: {e}", exc_info=True)

async def get_user_settings_db(user_id: int) -> dict:
    """
    Получает настройки пользователя из БД.
    Возвращает пустой словарь, если пользователь не найден или настройки отсутствуют/некорректны.
    """
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT settings FROM users WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        if result and result[0]:
            try:
                return json.loads(result[0])
            except json.JSONDecodeError:
                logger.error(f"Ошибка декодирования JSON настроек для пользователя {user_id}: {result[0]}")
                return {} # Возвращаем пустой словарь при ошибке декодирования
        return {} # Возвращаем пустой словарь, если пользователь не найден или поле settings пустое

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
    async with aiosqlite.connect(DB_NAME) as db:
        settings_json = json.dumps(settings)
        await db.execute("UPDATE users SET settings = ? WHERE user_id = ?", (settings_json, user_id))
        await db.commit()

async def add_favorite(user_id: int, code_path: str):
    """Добавляет пример кода в избранное."""
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            await db.execute("INSERT INTO user_favorites (user_id, code_path) VALUES (?, ?)", (user_id, code_path))
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            logger.warning(f"Попытка повторно добавить в избранное: user {user_id}, path {code_path}")
            return False # Уже существует

async def remove_favorite(user_id: int, code_path: str):
    """Удаляет пример кода из избранного."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM user_favorites WHERE user_id = ? AND code_path = ?", (user_id, code_path))
        await db.commit()

async def get_favorites(user_id: int) -> list:
    """Получает список избранных примеров кода для пользователя."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT code_path FROM user_favorites WHERE user_id = ? ORDER BY added_at DESC", (user_id,))
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


async def clear_latex_cache():
    """Clears all entries from the latex_cache table."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM latex_cache")
        await db.commit()
        logger.info("LaTeX cache table has been cleared.")

# --- GitHub Repos ---

async def add_user_repo(user_id: int, repo_path: str) -> bool:
    """Adds a GitHub repository to the user's list."""
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            await db.execute("INSERT INTO user_github_repos (user_id, repo_path) VALUES (?, ?)", (user_id, repo_path))
            await db.commit()
            logger.info(f"User {user_id} added repo {repo_path}")
            return True
        except aiosqlite.IntegrityError:
            logger.warning(f"Attempt to re-add repo for user {user_id}: {repo_path}")
            return False # Already exists

async def get_user_repos(user_id: int) -> list[str]:
    """Gets the list of GitHub repositories for a user."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT repo_path FROM user_github_repos WHERE user_id = ? ORDER BY added_at ASC", (user_id,))
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

async def remove_user_repo(user_id: int, repo_path: str) -> bool:
    """Removes a GitHub repository from the user's list."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("DELETE FROM user_github_repos WHERE user_id = ? AND repo_path = ?", (user_id, repo_path))
        await db.commit()
        deleted_rows = cursor.rowcount > 0
        if deleted_rows:
            logger.info(f"User {user_id} removed repo {repo_path}")
        return deleted_rows

async def update_user_repo(user_id: int, old_repo_path: str, new_repo_path: str):
    """Updates a user's repository path."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE user_github_repos SET repo_path = ? WHERE user_id = ? AND repo_path = ?", (new_repo_path, user_id, old_repo_path))
        await db.commit()
        logger.info(f"User {user_id} updated repo from {old_repo_path} to {new_repo_path}")

# --- Onboarding ---

async def is_onboarding_completed(user_id: int) -> bool:
    """Checks if the user has completed the onboarding process."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT onboarding_completed FROM users WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        # If user exists and flag is True, return True. Otherwise, False.
        return result[0] if result else False

async def set_onboarding_completed(user_id: int):
    """Marks the onboarding process as completed for a user."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET onboarding_completed = TRUE WHERE user_id = ?", (user_id,))
        await db.commit()
        logger.info(f"Onboarding marked as completed for user {user_id}")
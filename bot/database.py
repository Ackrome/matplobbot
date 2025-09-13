import aiosqlite
import datetime
import logging
import json
import os

DB_DIR = "/app/db_data"  # Путь внутри контейнера, где будет храниться БД
DB_NAME = os.path.join(DB_DIR, "user_actions.db")

logger = logging.getLogger(__name__)

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
                settings TEXT DEFAULT '{}' -- Новое поле для хранения настроек в JSON
            )
        ''')
        # Проверяем, существует ли столбец 'settings' (для обновления существующих БД)
        cursor = await db.execute("PRAGMA table_info(users);")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        if 'settings' not in column_names:
            await db.execute("ALTER TABLE users ADD COLUMN settings TEXT DEFAULT '{}';")
            logger.info("Добавлен столбец 'settings' в таблицу 'users'.")
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
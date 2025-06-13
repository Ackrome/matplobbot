import aiosqlite
import datetime
import logging
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
                avatar_pic_url TEXT
            )
        ''')
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
        await db.commit()
    logger.info(f"База данных {DB_NAME} инициализирована с таблицами users и user_actions.")

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
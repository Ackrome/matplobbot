# c:/Users/ivant/Desktop/proj/matplobbot/fastapi_stats_app/db_utils.py
import aiosqlite
import os
import logging
from fastapi import HTTPException
from .config import DB_PATH

logger = logging.getLogger(__name__)

def get_db_connection_obj():
    """
    Проверяет наличие файла БД и возвращает объект aiosqlite.connect(),
    который является awaitable context manager.
    """
    if not os.path.exists(DB_PATH):
        logger.warning(f"Файл базы данных {DB_PATH} еще не существует. Возможно, бот еще не создал его.")
        raise HTTPException(status_code=503, detail="База данных еще не инициализирована ботом. Пожалуйста, подождите или убедитесь, что бот запущен и работает корректно.")
    return aiosqlite.connect(DB_PATH)

async def get_leaderboard_data_from_db(db_conn):
    """Извлекает данные для таблицы лидеров из БД, включая аватар."""
    query = """
        SELECT
            u.user_id,
            u.full_name,
            COALESCE(u.username, 'Нет username') AS username,
            u.avatar_pic_url,
            COUNT(ua.id) AS actions_count,
            STRFTIME('%Y-%m-%d %H:%M:%S', MAX(ua.timestamp)) AS last_action_time
        FROM
            users u
        JOIN
            user_actions ua ON u.user_id = ua.user_id
        GROUP BY
            u.user_id, u.full_name, u.username, u.avatar_pic_url
        ORDER BY
            actions_count DESC
        LIMIT 100; -- Ограничиваем вывод для производительности
    """
    async with db_conn.execute(query) as cursor:
        rows = await cursor.fetchall()
        leaderboard = []
        for row_tuple in rows:
            leaderboard.append({
                "user_id": row_tuple[0],
                "full_name": row_tuple[1],
                "username": row_tuple[2],
                "avatar_pic_url": row_tuple[3],
                "actions_count": row_tuple[4],
                "last_action_time": row_tuple[5]
            })
        return leaderboard

async def get_popular_commands_data_from_db(db_conn):
    """Извлекает данные о популярных командах из БД."""
    query = """
        SELECT
            action_details as command,
            COUNT(id) as command_count
        FROM
            user_actions
        WHERE
            action_type = 'command'
        GROUP BY
            action_details
        ORDER BY
            command_count DESC
        LIMIT 10;
    """
    async with db_conn.execute(query) as cursor:
        rows = await cursor.fetchall()
        return [{"command": row[0], "count": row[1]} for row in rows]

async def get_popular_messages_data_from_db(db_conn):
    """Извлекает данные о популярных текстовых сообщениях из БД."""
    query = """
        SELECT
            CASE
                WHEN LENGTH(action_details) > 30 THEN SUBSTR(action_details, 1, 27) || '...'
                ELSE action_details
            END as message_snippet,
            COUNT(id) as message_count
        FROM
            user_actions
        WHERE
            action_type = 'text_message' AND action_details IS NOT NULL AND action_details != ''
        GROUP BY
            message_snippet
        ORDER BY
            message_count DESC
        LIMIT 10;
    """
    async with db_conn.execute(query) as cursor:
        rows = await cursor.fetchall()
        return [{"message": row[0], "count": row[1]} for row in rows]

async def get_action_types_distribution_from_db(db_conn):
    """Извлекает данные о распределении типов действий из БД."""
    query = """
        SELECT
            action_type,
            COUNT(id) as type_count
        FROM
            user_actions
        GROUP BY
            action_type
        ORDER BY
            type_count DESC;
    """
    async with db_conn.execute(query) as cursor:
        rows = await cursor.fetchall()
        return [{"action_type": row[0], "count": row[1]} for row in rows]

async def get_activity_over_time_data_from_db(db_conn, period='day'):
    """Извлекает данные об активности пользователей по времени (день, неделя, месяц) из БД."""
    date_format = '%Y-%m-%d' if period == 'day' else '%Y-%m'

    query = f"""
        SELECT
            STRFTIME('{date_format}', timestamp) as period_start,
            COUNT(id) as actions_count
        FROM user_actions
        GROUP BY period_start
        ORDER BY period_start ASC;
    """
    async with db_conn.execute(query) as cursor:
        rows = await cursor.fetchall()
        return [{"period": row[0], "count": row[1]} for row in rows]

async def get_user_profile_data_from_db(db_conn, user_id: int, page: int = 1, page_size: int = 50):
    """Извлекает детали профиля пользователя и пагинированный список его действий."""
    # Рассчитываем смещение для пагинации
    offset = (page - 1) * page_size

    # Запрос для деталей пользователя
    user_query = """
        SELECT
            user_id,
            full_name,
            COALESCE(username, 'Нет username') AS username,
            avatar_pic_url
        FROM
            users
        WHERE
            user_id = ?;
    """
    # Запрос для действий пользователя
    actions_query = """
        SELECT
            id,
            action_type,
            action_details,
            STRFTIME('%Y-%m-%d %H:%M:%S', timestamp) AS timestamp
        FROM
            user_actions
        WHERE
            user_id = ?
        ORDER BY
            timestamp DESC
        LIMIT ? OFFSET ?;
    """
    async with db_conn.execute(user_query, (user_id,)) as cursor:
        user_row = await cursor.fetchone()
        if not user_row:
            return None  # Пользователь не найден

    user_details = dict(zip([c[0] for c in cursor.description], user_row))

    # Получаем общее количество действий для пагинации
    total_actions_query = "SELECT COUNT(id) FROM user_actions WHERE user_id = ?;"
    async with db_conn.execute(total_actions_query, (user_id,)) as cursor:
        total_actions_row = await cursor.fetchone()
        total_actions = total_actions_row[0] if total_actions_row else 0

    # Получаем пагинированный список действий
    async with db_conn.execute(actions_query, (user_id, page_size, offset)) as cursor:
        actions_rows = await cursor.fetchall()
        actions = [dict(zip([c[0] for c in cursor.description], row)) for row in actions_rows]

    return {
        "user_details": user_details,
        "actions": actions,
        "total_actions": total_actions
    }
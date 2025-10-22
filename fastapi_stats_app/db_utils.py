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

async def get_user_profile_data_from_db(
    db_conn,
    user_id: int,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = 'timestamp',
    sort_order: str = 'desc'
):
    """Извлекает детали профиля пользователя и пагинированный список его действий."""
    # --- Безопасная сортировка ---
    allowed_sort_columns = ['id', 'action_type', 'action_details', 'timestamp']
    if sort_by not in allowed_sort_columns:
        sort_by = 'timestamp' # Значение по умолчанию
    sort_order = 'ASC' if sort_order.lower() == 'asc' else 'DESC' # Безопасное определение порядка

    # --- Единый запрос для получения всех данных ---
    # Используем CTE и оконные функции для эффективности.
    # 1. Выбираем все действия пользователя.
    # 2. С помощью оконной функции COUNT(*) OVER () получаем общее количество действий без дополнительного запроса.
    # 3. Присоединяем информацию о пользователе.
    # 4. Применяем пагинацию и сортировку.
    query = f"""
        WITH UserActions AS (
            SELECT
                id,
                action_type,
                action_details,
                STRFTIME('%Y-%m-%d %H:%M:%S', timestamp) AS timestamp
            FROM user_actions
            WHERE user_id = ?
        )
        SELECT
            u.user_id,
            u.full_name,
            COALESCE(u.username, 'Нет username') AS username,
            u.avatar_pic_url,
            (SELECT COUNT(*) FROM UserActions) as total_actions,
            ua.id as action_id,
            ua.action_type,
            ua.action_details,
            ua.timestamp
        FROM users u
        LEFT JOIN UserActions ua
        WHERE u.user_id = ?
        ORDER BY ua.{sort_by} {sort_order}
        LIMIT ? OFFSET ?;
    """
    offset = (page - 1) * page_size
    async with db_conn.execute(query, (user_id, user_id, page_size, offset)) as cursor:
        rows = await cursor.fetchall()
        if not rows:
            return None  # Пользователь не найден

    first_row = rows[0]
    user_details = {
        "user_id": first_row[0],
        "full_name": first_row[1],
        "username": first_row[2],
        "avatar_pic_url": first_row[3]
    }
    total_actions = first_row[4]

    # Собираем действия, если они есть (может быть пользователь без действий)
    actions = []
    for row in rows:
        if row[5] is not None: # action_id не NULL
            actions.append({
                "id": row[5],
                "action_type": row[6],
                "action_details": row[7],
                "timestamp": row[8]
            })

    return {
        "user_details": user_details,
        "actions": actions,
        "total_actions": total_actions
    }
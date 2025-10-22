import asyncpg
import os
import logging
from fastapi import HTTPException
from .config import DATABASE_URL

logger = logging.getLogger(__name__)

# Global connection pool
pool = None

async def init_db_pool():
    global pool
    if pool is None:
        try:
            pool = await asyncpg.create_pool(DATABASE_URL, min_size=5, max_size=20)
            logger.info("Database connection pool created successfully.")
        except Exception as e:
            logger.error(f"Failed to create database connection pool: {e}", exc_info=True)
            raise

async def close_db_pool():
    global pool
    if pool:
        await pool.close()
        logger.info("Database connection pool closed.")

def get_db_connection_obj():
    """
    Acquires a connection from the pool. This is an awaitable context manager.
    """
    if pool is None:
        raise HTTPException(status_code=503, detail="Database connection pool is not initialized.")
    return pool.acquire()

async def get_leaderboard_data_from_db(db_conn):
    """Извлекает данные для таблицы лидеров из БД, включая аватар."""
    query = """
        SELECT
            u.user_id,
            u.full_name,
            COALESCE(u.username, 'Нет username') AS username,
            u.avatar_pic_url,
            COUNT(ua.id)::int AS actions_count,
            TO_CHAR(MAX(ua.timestamp), 'YYYY-MM-DD HH24:MI:SS') AS last_action_time
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
    rows = await db_conn.fetch(query)
    # asyncpg returns a list of Record objects, which behave like dicts
    return [dict(row) for row in rows]

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
    rows = await db_conn.fetch(query)
    return [{"command": row['command'], "count": row['command_count']} for row in rows]

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
    rows = await db_conn.fetch(query)
    return [{"message": row['message_snippet'], "count": row['message_count']} for row in rows]

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
    rows = await db_conn.fetch(query)
    return [{"action_type": row['action_type'], "count": row['type_count']} for row in rows]

async def get_activity_over_time_data_from_db(db_conn, period='day'):
    """Извлекает данные об активности пользователей по времени (день, неделя, месяц) из БД."""
    if period == 'week':
        date_format = 'IYYY-IW'  # ISO Week format for PostgreSQL
    elif period == 'month':
        date_format = 'YYYY-MM'
    else:  # Default to 'day'
        date_format = 'YYYY-MM-DD'

    query = f"""
        SELECT
            TO_CHAR(timestamp, '{date_format}') as period_start,
            COUNT(id) as actions_count
        FROM user_actions
        GROUP BY period_start
        ORDER BY period_start ASC;
    """
    rows = await db_conn.fetch(query)
    return [{"period": row['period_start'], "count": row['actions_count']} for row in rows]

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
    allowed_sort_columns = ['id', 'action_type', 'action_details', 'timestamp'] # These are ua columns
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
                TO_CHAR(timestamp, 'YYYY-MM-DD HH24:MI:SS') AS timestamp
            FROM user_actions
            WHERE user_id = $1
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
        LEFT JOIN UserActions ua ON 1=1
        WHERE u.user_id = $2
        ORDER BY ua.{sort_by} {sort_order}
        LIMIT $3 OFFSET $4;
    """
    offset = (page - 1) * page_size
    rows = await db_conn.fetch(query, user_id, user_id, page_size, offset)
    if not rows:
        # If user exists but has no actions, we might get no rows. Check user existence separately.
        user_exists = await db_conn.fetchrow("SELECT 1 FROM users WHERE user_id = $1", user_id)
        if not user_exists:
            return None # User not found
        # User exists but has no actions, return empty actions list
        user_details_row = await db_conn.fetchrow("SELECT user_id, full_name, COALESCE(username, 'Нет username') AS username, avatar_pic_url FROM users WHERE user_id = $1", user_id)
        return {
            "user_details": dict(user_details_row),
            "actions": [],
            "total_actions": 0
        }

    first_row = dict(rows[0])
    user_details = {
        "user_id": first_row["user_id"],
        "full_name": first_row["full_name"],
        "username": first_row["username"],
        "avatar_pic_url": first_row["avatar_pic_url"]
    }
    total_actions = first_row["total_actions"]

    # Собираем действия, если они есть (может быть пользователь без действий)
    actions = []
    for row in rows:
        row_dict = dict(row)
        if row_dict["action_id"] is not None: # action_id не NULL
            actions.append({
                "id": row_dict["action_id"],
                "action_type": row_dict["action_type"],
                "action_details": row_dict["action_details"],
                "timestamp": row_dict["timestamp"]
            })

    return {
        "user_details": user_details,
        "actions": actions,
        "total_actions": total_actions
    }

async def get_users_for_action(db_conn, action_type: str, action_details: str, page: int = 1, page_size: int = 15, sort_by: str = 'full_name', sort_order: str = 'asc'):
    """Извлекает пагинированный список уникальных пользователей, совершивших определенное действие."""
    # Note: action_type for messages is 'text_message' in the DB
    db_action_type = 'text_message' if action_type == 'message' else action_type
    offset = (page - 1) * page_size

    # --- Безопасная сортировка ---
    allowed_sort_columns = ['user_id', 'full_name', 'username'] # These are u columns
    if sort_by not in allowed_sort_columns:
        sort_by = 'full_name' # Значение по умолчанию
    sort_order = 'DESC' if sort_order.lower() == 'desc' else 'ASC' # Безопасное определение порядка
    order_by_clause = f"ORDER BY u.{sort_by} {sort_order}"

    # Query for total count of distinct users
    count_query = """
        SELECT COUNT(DISTINCT u.user_id)
        FROM users u
        JOIN user_actions ua ON u.user_id = ua.user_id
        WHERE ua.action_type = $1 AND ua.action_details = $2;
    """
    total_users = await db_conn.fetchval(count_query, db_action_type, action_details)

    # Query for the paginated list of users
    users_query = f"""
        SELECT DISTINCT
            u.user_id,
            u.full_name,
            COALESCE(u.username, 'Нет username') AS username
        FROM users u
        JOIN user_actions ua ON u.user_id = ua.user_id
        WHERE ua.action_type = $1 AND ua.action_details = $2
        {order_by_clause}
        LIMIT $3 OFFSET $4;
    """
    rows = await db_conn.fetch(users_query, db_action_type, action_details, page_size, offset)
    users = [dict(row) for row in rows]

    return {
        "users": users,
        "total_users": total_users
    }
import asyncpg
import datetime
import logging
import json
import os

logger = logging.getLogger(__name__)

# --- PostgreSQL Database Configuration ---
# The DATABASE_URL should be a complete connection string.
# Example for Docker: postgresql://user:password@postgres:5432/matplobbot_db
# Example for local:  postgresql://user:password@localhost:5432/matplobbot_db
DATABASE_URL = os.getenv("DATABASE_URL")

# Global connection pool
pool = None

async def init_db_pool():
    global pool
    if pool is None:
        try:
            if not DATABASE_URL:
                logger.critical("DATABASE_URL environment variable is not set. Cannot initialize database pool.")
                raise ValueError("DATABASE_URL is not set.")
            pool = await asyncpg.create_pool(DATABASE_URL, min_size=5, max_size=20)
            logger.info("Shared DB Pool: Database connection pool created successfully.")
        except Exception as e:
            logger.error(f"Failed to create database connection pool: {e}", exc_info=True)
            raise

async def close_db_pool():
    global pool
    if pool:
        await pool.close()
        logger.info("Shared DB Pool: Database connection pool closed.")

def get_db_connection_obj():
    if pool is None:
        # In FastAPI context, this would be an HTTPException
        raise ConnectionError("Database connection pool is not initialized.")
    return pool.acquire()

# --- User Settings Defaults ---
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
                code_path TEXT NOT NULL,
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
                repo_path TEXT NOT NULL,
                added_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, repo_path)
            )
            ''')
            await connection.execute('''
            CREATE TABLE IF NOT EXISTS user_schedule_subscriptions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                entity_name TEXT NOT NULL,
                notification_time TIME NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                last_schedule_hash TEXT, -- Added here for consistency
                UNIQUE(user_id, entity_type, entity_id)
            )
            ''')
            # Add the last_schedule_hash column if it doesn't exist, for backward compatibility
    logger.info("Database tables initialized.")

async def log_user_action(user_id: int, username: str | None, full_name: str, avatar_pic_url: str | None, action_type: str, action_details: str | None):
    async with pool.acquire() as connection:
        try:
            await connection.execute('''
                INSERT INTO users (user_id, username, full_name, avatar_pic_url)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    full_name = EXCLUDED.full_name,
                    avatar_pic_url = EXCLUDED.avatar_pic_url;
            ''', user_id, username, full_name, avatar_pic_url)
            await connection.execute('''
                INSERT INTO user_actions (user_id, action_type, action_details)
                VALUES ($1, $2, $3);
            ''', user_id, action_type, action_details)
        except Exception as e:
            logger.error(f"Error logging user action to DB: {e}", exc_info=True)

async def get_user_settings(user_id: int) -> dict:
    async with pool.acquire() as connection:
        settings_json = await connection.fetchval("SELECT settings FROM users WHERE user_id = $1", user_id)
        db_settings = json.loads(settings_json) if settings_json else {}
    merged_settings = DEFAULT_SETTINGS.copy()
    merged_settings.update(db_settings)
    return merged_settings

async def update_user_settings_db(user_id: int, settings: dict):
    async with pool.acquire() as connection:
        await connection.execute("UPDATE users SET settings = $1 WHERE user_id = $2", json.dumps(settings), user_id)

# --- Favorites ---
async def add_favorite(user_id: int, code_path: str):
    async with pool.acquire() as connection:
        try:
            await connection.execute("INSERT INTO user_favorites (user_id, code_path) VALUES ($1, $2)", user_id, code_path)
            return True
        except asyncpg.UniqueViolationError:
            return False

async def remove_favorite(user_id: int, code_path: str):
    async with pool.acquire() as connection:
        await connection.execute("DELETE FROM user_favorites WHERE user_id = $1 AND code_path = $2", user_id, code_path)

async def get_favorites(user_id: int) -> list:
    async with pool.acquire() as connection:
        rows = await connection.fetch("SELECT code_path FROM user_favorites WHERE user_id = $1", user_id)
        return [row['code_path'] for row in rows]

# --- LaTeX Cache ---
async def clear_latex_cache():
    async with pool.acquire() as connection:
        await connection.execute("TRUNCATE TABLE latex_cache")

# --- GitHub Repos ---
async def add_user_repo(user_id: int, repo_path: str) -> bool:
    async with pool.acquire() as connection:
        try:
            await connection.execute("INSERT INTO user_github_repos (user_id, repo_path) VALUES ($1, $2)", user_id, repo_path)
            return True
        except asyncpg.UniqueViolationError:
            return False

async def get_user_repos(user_id: int) -> list[str]:
    async with pool.acquire() as connection:
        rows = await connection.fetch("SELECT repo_path FROM user_github_repos WHERE user_id = $1 ORDER BY added_at ASC", user_id)
        return [row['repo_path'] for row in rows]

async def remove_user_repo(user_id: int, repo_path: str):
    async with pool.acquire() as connection:
        await connection.execute("DELETE FROM user_github_repos WHERE user_id = $1 AND repo_path = $2", user_id, repo_path)

async def update_user_repo(user_id: int, old_repo_path: str, new_repo_path: str):
    async with pool.acquire() as connection:
        await connection.execute("UPDATE user_github_repos SET repo_path = $1 WHERE user_id = $2 AND repo_path = $3", new_repo_path, user_id, old_repo_path)

# --- Onboarding ---
async def is_onboarding_completed(user_id: int) -> bool:
    async with pool.acquire() as connection:
        completed = await connection.fetchval("SELECT onboarding_completed FROM users WHERE user_id = $1", user_id)
        return completed or False

async def set_onboarding_completed(user_id: int):
    async with pool.acquire() as connection:
        await connection.execute("UPDATE users SET onboarding_completed = TRUE WHERE user_id = $1", user_id)

# --- Schedule Subscriptions ---
async def add_schedule_subscription(user_id: int, entity_type: str, entity_id: str, entity_name: str, notification_time: datetime.time) -> bool:
    async with pool.acquire() as connection:
        try:
            await connection.execute('''
                INSERT INTO user_schedule_subscriptions (user_id, entity_type, entity_id, entity_name, notification_time)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id, entity_type, entity_id) DO UPDATE SET
                    entity_name = EXCLUDED.entity_name,
                    notification_time = EXCLUDED.notification_time,
                    is_active = TRUE;
            ''', user_id, entity_type, entity_id, entity_name, notification_time)
            return True
        except Exception as e:
            logger.error(f"Failed to add schedule subscription for user {user_id}: {e}", exc_info=True)
            return False
 
async def get_user_subscriptions(user_id: int, page: int = 0, page_size: int = 5) -> tuple[list, int]:
    """
    Gets a paginated list of active schedule subscriptions for a specific user.
    Returns a tuple: (list of subscriptions, total count).
    """
    if not pool:
        raise ConnectionError("Database pool is not initialized.")
    async with pool.acquire() as connection:
        # Query to get the paginated list
        offset = page * page_size
        rows = await connection.fetch("""
            SELECT id, entity_type, entity_id, entity_name, TO_CHAR(notification_time, 'HH24:MI') as notification_time
            FROM user_schedule_subscriptions
            WHERE user_id = $1 AND is_active = TRUE
            ORDER BY entity_name, notification_time
            LIMIT $2 OFFSET $3
        """, user_id, page_size, offset)
        
        # Query to get the total count for pagination
        total_count = await connection.fetchval("SELECT COUNT(*) FROM user_schedule_subscriptions WHERE user_id = $1 AND is_active = TRUE", user_id)

        return [dict(row) for row in rows], total_count or 0

async def remove_schedule_subscription(subscription_id: int, user_id: int) -> str | None:
    """
    Removes a specific schedule subscription for a user, ensuring ownership.
    Returns the entity_name of the deleted subscription on success, otherwise None.
    """
    if not pool:
        raise ConnectionError("Database pool is not initialized.")
    async with pool.acquire() as connection:
        deleted_name = await connection.fetchval(
            "DELETE FROM user_schedule_subscriptions WHERE id = $1 AND user_id = $2 RETURNING entity_name",
            subscription_id, user_id)
        return deleted_name

async def get_subscriptions_for_notification(notification_time: str) -> list:
    async with pool.acquire() as connection:
        # Modified to select the subscription ID and the last hash
        rows = await connection.fetch("""
            SELECT id, user_id, entity_type, entity_id, entity_name, last_schedule_hash
            FROM user_schedule_subscriptions
            WHERE is_active = TRUE AND TO_CHAR(notification_time, 'HH24:MI') = $1
        """, notification_time)
        return [dict(row) for row in rows]

async def get_all_active_subscriptions() -> list:
    """Fetches all active schedule subscriptions from the database."""
    if not pool:
        raise ConnectionError("Database pool is not initialized.")
    async with pool.acquire() as connection:
        rows = await connection.fetch("""
            SELECT id, user_id, entity_type, entity_id, entity_name, last_schedule_hash
            FROM user_schedule_subscriptions WHERE is_active = TRUE
        """)
        return [dict(row) for row in rows]

async def update_subscription_hash(subscription_id: int, new_hash: str):
    """Updates the schedule hash for a specific subscription."""
    if not pool:
        raise ConnectionError("Database pool is not initialized.")
    async with pool.acquire() as connection:
        await connection.execute("UPDATE user_schedule_subscriptions SET last_schedule_hash = $1 WHERE id = $2", new_hash, subscription_id)

# --- FastAPI Specific Queries ---
async def get_leaderboard_data_from_db(db_conn):
    # The timestamp is stored in UTC (TIMESTAMPTZ). We convert it to Moscow time for display.
    query = """
        SELECT
            u.user_id,
            u.full_name,
            COALESCE(u.username, 'N/A') AS username,
            u.avatar_pic_url,
            COUNT(ua.id)::int AS actions_count,
            TO_CHAR(MAX(ua.timestamp AT TIME ZONE 'Europe/Moscow'), 'YYYY-MM-DD HH24:MI:SS') AS last_action_time
        FROM users u
        JOIN user_actions ua ON u.user_id = ua.user_id
        GROUP BY u.user_id, u.full_name, u.username, u.avatar_pic_url
        ORDER BY actions_count DESC LIMIT 100;
    """
    rows = await db_conn.fetch(query)
    return [dict(row) for row in rows]

async def get_popular_commands_data_from_db(db_conn):
    query = """
        SELECT action_details as command, COUNT(id) as command_count FROM user_actions
        WHERE action_type = 'command' GROUP BY action_details ORDER BY command_count DESC LIMIT 10;
    """
    rows = await db_conn.fetch(query)
    return [{"command": row['command'], "count": row['command_count']} for row in rows]

async def get_popular_messages_data_from_db(db_conn):
    query = """
        SELECT CASE WHEN LENGTH(action_details) > 30 THEN SUBSTR(action_details, 1, 27) || '...' ELSE action_details END as message_snippet,
        COUNT(id) as message_count FROM user_actions
        WHERE action_type = 'text_message' AND action_details IS NOT NULL AND action_details != ''
        GROUP BY message_snippet ORDER BY message_count DESC LIMIT 10;
    """
    rows = await db_conn.fetch(query)
    return [{"message": row['message_snippet'], "count": row['message_count']} for row in rows]

async def get_action_types_distribution_from_db(db_conn):
    query = "SELECT action_type, COUNT(id) as type_count FROM user_actions GROUP BY action_type ORDER BY type_count DESC;"
    rows = await db_conn.fetch(query)
    return [{"action_type": row['action_type'], "count": row['type_count']} for row in rows]

async def get_activity_over_time_data_from_db(db_conn, period='day'):
    date_format = {'day': 'YYYY-MM-DD', 'week': 'IYYY-IW', 'month': 'YYYY-MM'}.get(period, 'YYYY-MM-DD')
    # Convert timestamp to Moscow time before grouping
    query = f"""
        SELECT TO_CHAR(timestamp AT TIME ZONE 'Europe/Moscow', '{date_format}') as period_start, COUNT(id) as actions_count 
        FROM user_actions GROUP BY period_start ORDER BY period_start ASC;
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
                TO_CHAR(timestamp AT TIME ZONE 'Europe/Moscow', 'YYYY-MM-DD HH24:MI:SS') AS timestamp
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

async def get_all_user_actions(db_conn, user_id: int):
    """Извлекает ВСЕ действия для указанного пользователя без пагинации."""
    query = """
        SELECT
            id,
            action_type,
            action_details,
            TO_CHAR(timestamp AT TIME ZONE 'Europe/Moscow', 'YYYY-MM-DD HH24:MI:SS') AS timestamp
        FROM user_actions
        WHERE user_id = $1
        ORDER BY timestamp DESC;
    """
    rows = await db_conn.fetch(query, user_id)
    return [dict(row) for row in rows]
import asyncpg
import datetime
import logging
import json
import os
from .redis_client import redis_client

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

class SubscriptionConflictError(Exception):
    """Raised when updating a subscription would violate a unique constraint."""
    pass

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
    'show_schedule_emojis': True,
    'show_lecturer_emails': True, 
    'use_short_names': True,
    'admin_daily_summary_time': '09:00', # Default time for admin summary
    'admin_summary_days': [0, 1, 2, 3, 4], # NEW: Mon-Fri by default
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
                chat_id BIGINT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                entity_name TEXT NOT NULL,
                notification_time TIME NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                last_schedule_hash TEXT,
                deactivated_at TIMESTAMPTZ DEFAULT NULL,
                message_thread_id BIGINT DEFAULT NULL,
                added_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, entity_type, entity_id, notification_time)
            )
            ''')
            await connection.execute('''
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id BIGINT PRIMARY KEY,
                settings JSONB DEFAULT '{}'::jsonb
            )
            ''')
            await connection.execute('''
            CREATE TABLE IF NOT EXISTS discipline_short_names (
                id SERIAL PRIMARY KEY,
                full_name TEXT NOT NULL UNIQUE,
                short_name TEXT NOT NULL,
                approved_by BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
                approved_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            await connection.execute('''
            CREATE TABLE IF NOT EXISTS user_disabled_short_names (
                user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                short_name_id INT NOT NULL REFERENCES discipline_short_names(id) ON DELETE CASCADE,
                PRIMARY KEY (user_id, short_name_id)
            )
            ''')



    logger.info("Database tables initialized.")


async def log_user_action(user_id: int, username: str | None, full_name: str | None, avatar_pic_url: str | None, action_type: str, action_details: str | None):
    async with pool.acquire() as connection:
        try:
            # 1. Вставляем действие
            row = await connection.fetchrow('''
                INSERT INTO user_actions (user_id, action_type, action_details)
                VALUES ($1, $2, $3)
                RETURNING id, timestamp;
            ''', user_id, action_type, action_details)

            # 2. Обновляем пользователя (если это не админское сообщение)
            if full_name and full_name != "Admin" and full_name != "System":
                await connection.execute('''
                    INSERT INTO users (user_id, username, full_name, avatar_pic_url)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username = EXCLUDED.username,
                        full_name = EXCLUDED.full_name,
                        avatar_pic_url = EXCLUDED.avatar_pic_url;
                ''', user_id, username, full_name, avatar_pic_url)
            else:
                await connection.execute('''
                    INSERT INTO users (user_id, full_name)
                    VALUES ($1, 'Unknown User')
                    ON CONFLICT(user_id) DO NOTHING;
                ''', user_id)

            # --- 3. НОВОЕ: Публикуем событие в Redis ---
            # Формируем payload, который похож на то, что отдает API
            payload = {
                "id": row['id'],
                "action_type": action_type,
                "action_details": action_details,
                "timestamp": row['timestamp'].isoformat()
            }
            # Публикуем в канал user_updates:{user_id}
            await redis_client.client.publish(f"user_updates:{user_id}", json.dumps(payload))

        except Exception as e:
            logger.error(f"Error logging user action to DB: {e}", exc_info=True)
            
async def get_user_settings(user_id: int) -> dict:
    async with pool.acquire() as connection:
        settings_json = await connection.fetchval("SELECT settings FROM users WHERE user_id = $1", user_id)
        db_settings = json.loads(settings_json) if settings_json else {}
    merged_settings = DEFAULT_SETTINGS.copy()
    merged_settings.update(db_settings)
    return merged_settings

async def get_chat_settings(chat_id: int) -> dict:
    """Fetches settings for a specific chat, creating a default record if none exists."""
    async with pool.acquire() as connection:
        # Upsert to ensure a row exists for the chat.
        await connection.execute("""
            INSERT INTO chat_settings (chat_id) VALUES ($1)
            ON CONFLICT (chat_id) DO NOTHING;
        """, chat_id)
        settings_json = await connection.fetchval("SELECT settings FROM chat_settings WHERE chat_id = $1", chat_id)
        db_settings = json.loads(settings_json) if settings_json else {}
    # Merge with defaults to ensure all keys are present.
    merged_settings = DEFAULT_SETTINGS.copy()
    merged_settings.update(db_settings)
    return merged_settings

async def update_user_settings_db(user_id: int, settings: dict):
    async with pool.acquire() as connection:
        await connection.execute("UPDATE users SET settings = $1 WHERE user_id = $2", json.dumps(settings), user_id)

async def update_chat_settings_db(chat_id: int, settings: dict):
    async with pool.acquire() as connection:
        await connection.execute("UPDATE chat_settings SET settings = $1 WHERE chat_id = $2", json.dumps(settings), chat_id)

async def delete_all_user_data(user_id: int) -> bool:
    """
    Deletes a user and all their associated data from the database.
    This leverages ON DELETE CASCADE constraints on foreign keys.
    Returns True on success, False otherwise.
    """
    if not pool:
        raise ConnectionError("Database pool is not initialized.")
    async with pool.acquire() as connection:
        # Deleting the user from the 'users' table will cascade to all other tables.
        result = await connection.execute("DELETE FROM users WHERE user_id = $1", user_id)
        return result.endswith('1') # "DELETE 1" indicates one row was deleted.

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
async def add_schedule_subscription(user_id: int, chat_id: int, message_thread_id: int | None, entity_type: str, entity_id: str, entity_name: str, notification_time: datetime.time) -> int | None:
    """Adds or updates a subscription and returns its ID."""
    async with pool.acquire() as connection:
        try:
            # Use RETURNING id to get the ID of the inserted or updated row.
            subscription_id = await connection.fetchval('''
                INSERT INTO user_schedule_subscriptions (user_id, chat_id, message_thread_id, entity_type, entity_id, entity_name, notification_time)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (chat_id, entity_type, entity_id, notification_time) DO UPDATE SET
                    entity_name = EXCLUDED.entity_name,
                    is_active = TRUE,
                    user_id = EXCLUDED.user_id
                RETURNING id;
            ''', user_id, chat_id, message_thread_id, entity_type, entity_id, entity_name, notification_time)
            return subscription_id
        except Exception as e:
            logger.error(f"Failed to add schedule subscription for user {user_id}: {e}", exc_info=True)
            return None
 
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
            SELECT id, user_id, chat_id, entity_type, entity_id, entity_name, TO_CHAR(notification_time, 'HH24:MI') as notification_time, is_active
            FROM user_schedule_subscriptions
            WHERE user_id = $1
            ORDER BY entity_name, notification_time
            LIMIT $2 OFFSET $3
        """, user_id, page_size, offset)
        
        # Query to get the total count for pagination
        total_count = await connection.fetchval("SELECT COUNT(*) FROM user_schedule_subscriptions WHERE user_id = $1", user_id)

        return [dict(row) for row in rows], total_count or 0

async def get_chat_subscriptions(chat_id: int, page: int = 0, page_size: int = 5) -> tuple[list, int]:
    """
    Gets a paginated list of active schedule subscriptions for a specific chat.
    Returns a tuple: (list of subscriptions, total count).
    """
    if not pool:
        raise ConnectionError("Database pool is not initialized.")
    async with pool.acquire() as connection:
        offset = page * page_size
        rows = await connection.fetch("""
            SELECT id, user_id, chat_id, entity_type, entity_id, entity_name, TO_CHAR(notification_time, 'HH24:MI') as notification_time, is_active
            FROM user_schedule_subscriptions
            WHERE chat_id = $1
            ORDER BY entity_name, notification_time
            LIMIT $2 OFFSET $3
        """, chat_id, page_size, offset)
        
        total_count = await connection.fetchval("SELECT COUNT(*) FROM user_schedule_subscriptions WHERE chat_id = $1", chat_id)

        return [dict(row) for row in rows], total_count or 0

async def toggle_subscription_status(subscription_id: int, user_id: int, is_chat_admin: bool = False) -> tuple[bool, str] | None:
    """
    Toggles the is_active status of a subscription, checking for ownership or admin rights.
    Returns a tuple of (new_status, entity_name) on success, otherwise None.
    """
    if not pool:
        raise ConnectionError("Database pool is not initialized.")
    async with pool.acquire() as connection:
        # First, verify the user has permission if they are not a chat admin
        if not is_chat_admin:
            owner_id = await connection.fetchval("SELECT user_id FROM user_schedule_subscriptions WHERE id = $1", subscription_id)
            if owner_id != user_id:
                logger.warning(f"User {user_id} attempted to toggle subscription {subscription_id} without permission.")
                return None

        # If permission is granted, toggle the status and return the new state
        result = await connection.fetchrow(
            """
            UPDATE user_schedule_subscriptions
            SET is_active = NOT is_active,
                deactivated_at = CASE WHEN is_active THEN NOW() ELSE NULL END
            WHERE id = $1
            RETURNING is_active, entity_name
            """,
            subscription_id
        )
        return (result['is_active'], result['entity_name']) if result else None

async def remove_schedule_subscription(subscription_id: int, user_id: int, is_chat_admin: bool = False) -> str | None:
    """
    Removes a specific schedule subscription, checking for ownership or admin rights.
    - If is_chat_admin is False, it only deletes if user_id matches the creator.
    - If is_chat_admin is True, it deletes regardless of the creator.
    Returns the entity_name of the deleted subscription on success, otherwise None.
    """
    if not pool:
        raise ConnectionError("Database pool is not initialized.")
    async with pool.acquire() as connection:
        if is_chat_admin:
            # Admin can delete any subscription in their chat.
            deleted_name = await connection.fetchval(
                "DELETE FROM user_schedule_subscriptions WHERE id = $1 RETURNING entity_name",
                subscription_id)
        else:
            # Regular user can only delete their own subscriptions.
            deleted_name = await connection.fetchval(
                "DELETE FROM user_schedule_subscriptions WHERE id = $1 AND user_id = $2 RETURNING entity_name",
                subscription_id, user_id)
        return deleted_name

async def update_subscription_notification_time(subscription_id: int, new_time: datetime.time, user_id: int, is_chat_admin: bool = False) -> str | None:
    """
    Updates the notification time for a specific subscription, checking for ownership or admin rights.
    Returns the entity_name of the updated subscription on success, otherwise None.
    """
    if not pool:
        raise ConnectionError("Database pool is not initialized.")
    async with pool.acquire() as connection:
        if is_chat_admin:
            # Admin can update any subscription in their chat.
            updated_name = await connection.fetchval(
                "UPDATE user_schedule_subscriptions SET notification_time = $1 WHERE id = $2 RETURNING entity_name",
                new_time, subscription_id
            )
        else:
            # Regular user can only update their own subscriptions.
            updated_name = await connection.fetchval(
                "UPDATE user_schedule_subscriptions SET notification_time = $1 WHERE id = $2 AND user_id = $3 RETURNING entity_name",
                new_time, subscription_id, user_id
            )
        return updated_name


async def delete_old_inactive_subscriptions(days_inactive: int = 30):
    """
    Deletes subscriptions that have been inactive for more than a specified number of days.
    Returns the number of deleted subscriptions.
    """
    if not pool:
        raise ConnectionError("Database pool is not initialized.")
    async with pool.acquire() as connection:
        result = await connection.execute(
            "DELETE FROM user_schedule_subscriptions WHERE is_active = FALSE AND deactivated_at < NOW() - INTERVAL '$1 days'",
            str(days_inactive)
        )
        return int(result.split(' ')[-1]) # Returns "DELETE N", we want N

async def get_subscriptions_for_notification(notification_time: str) -> list:
    async with pool.acquire() as connection:
        # Modified to select the subscription ID and the last hash
        # Also select chat_id to know where to send the message
        rows = await connection.fetch("""
            SELECT id, user_id, chat_id, message_thread_id, entity_type, entity_id, entity_name, last_schedule_hash
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
            SELECT id, user_id, chat_id, message_thread_id, entity_type, entity_id, entity_name, last_schedule_hash
            FROM user_schedule_subscriptions WHERE is_active = TRUE
        """)
        return [dict(row) for row in rows]

async def get_unique_active_subscription_entities() -> list:
    """Fetches all unique active subscription entities from the database."""
    if not pool:
        raise ConnectionError("Database pool is not initialized.")
    async with pool.acquire() as connection:
        rows = await connection.fetch("""
            SELECT DISTINCT entity_type, entity_id, entity_name
            FROM user_schedule_subscriptions WHERE is_active = TRUE
        """)
        return [dict(row) for row in rows]

async def get_subscriptions_for_entity(entity_type: str, entity_id: str) -> list:
    """Fetches all active subscriptions for a specific entity."""
    if not pool:
        raise ConnectionError("Database pool is not initialized.")
    async with pool.acquire() as connection:
        rows = await connection.fetch("""
            SELECT id, user_id, chat_id, message_thread_id, entity_name, last_schedule_hash FROM user_schedule_subscriptions
            WHERE is_active = TRUE AND entity_type = $1 AND entity_id = $2
        """, entity_type, entity_id)
        return [dict(row) for row in rows]

async def update_subscription_hash(subscription_id: int, new_hash: str):
    """Updates the schedule hash for a specific subscription."""
    if not pool:
        raise ConnectionError("Database pool is not initialized.")
    async with pool.acquire() as connection:
        await connection.execute("UPDATE user_schedule_subscriptions SET last_schedule_hash = $1 WHERE id = $2", new_hash, subscription_id)

# --- Discipline Short Names ---
async def add_short_name(full_name: str, short_name: str, admin_id: int):
    """Adds or updates a short name mapping for a discipline."""
    async with pool.acquire() as connection:
        await connection.execute("""
            INSERT INTO discipline_short_names (full_name, short_name, approved_by)
            VALUES ($1, $2, $3)
            ON CONFLICT (full_name) DO UPDATE SET
                short_name = EXCLUDED.short_name,
                approved_by = EXCLUDED.approved_by,
                approved_at = CURRENT_TIMESTAMP;
        """, full_name, short_name, admin_id)

async def get_all_short_names() -> dict[str, str]:
    """Fetches all approved short name mappings."""
    async with pool.acquire() as connection:
        rows = await connection.fetch("SELECT full_name, short_name FROM discipline_short_names")
        return {row['full_name']: row['short_name'] for row in rows}

async def get_disabled_short_names_for_user(user_id: int) -> set[int]:
    """Fetches the set of short_name_ids disabled by a specific user."""
    if not pool:
        raise ConnectionError("Database pool is not initialized.")
    async with pool.acquire() as connection:
        rows = await connection.fetch("SELECT short_name_id FROM user_disabled_short_names WHERE user_id = $1", user_id)
        return {row['short_name_id'] for row in rows}

async def toggle_short_name_for_user(user_id: int, short_name_id: int) -> bool:
    """Toggles the disabled status of a short name for a user. Returns True if it's now disabled, False if enabled."""
    if not pool:
        raise ConnectionError("Database pool is not initialized.")
    async with pool.acquire() as connection:
        # Check if it exists
        exists = await connection.fetchval("SELECT 1 FROM user_disabled_short_names WHERE user_id = $1 AND short_name_id = $2", user_id, short_name_id)
        if exists:
            await connection.execute("DELETE FROM user_disabled_short_names WHERE user_id = $1 AND short_name_id = $2", user_id, short_name_id)
            return False # It is now enabled
        else:
            await connection.execute("INSERT INTO user_disabled_short_names (user_id, short_name_id) VALUES ($1, $2)", user_id, short_name_id)
            return True # It is now disabled

async def get_all_short_names_with_ids(page: int = 0, page_size: int = 5) -> tuple[list[dict], int]:
    """
    Fetches a paginated list of all approved short names with their IDs.
    Returns a tuple: (list of short names, total count).
    """
    if not pool:
        raise ConnectionError("Database pool is not initialized.")
    async with pool.acquire() as connection:
        offset = page * page_size
        rows = await connection.fetch("""
            SELECT id, full_name, short_name FROM discipline_short_names 
            ORDER BY full_name LIMIT $1 OFFSET $2
        """, page_size, offset)
        
        total_count = await connection.fetchval("SELECT COUNT(*) FROM discipline_short_names")
        
        return [dict(row) for row in rows], total_count or 0

async def delete_short_name_by_id(short_name_id: int) -> bool:
    """Deletes a short name mapping by its ID."""
    if not pool:
        raise ConnectionError("Database pool is not initialized.")
    async with pool.acquire() as connection:
        result = await connection.execute("DELETE FROM discipline_short_names WHERE id = $1", short_name_id)
        return result.endswith('1') # "DELETE 1" indicates one row was deleted.

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

async def get_admin_daily_summary(db_conn) -> dict:
    """Fetches a summary of today's stats for the admin report."""
    moscow_tz = 'Europe/Moscow'
    
    # New users today
    new_users_query = f"""
        WITH FirstActions AS (
            SELECT user_id, MIN(timestamp AT TIME ZONE '{moscow_tz}') as first_action_time
            FROM user_actions GROUP BY user_id
        )
        SELECT COUNT(user_id) FROM FirstActions WHERE DATE(first_action_time) = CURRENT_DATE;
    """
    
    # Total actions today
    total_actions_query = f"SELECT COUNT(id) FROM user_actions WHERE DATE(timestamp AT TIME ZONE '{moscow_tz}') = CURRENT_DATE;"
    
    # New suggestions today
    new_suggestions_query = f"SELECT COUNT(id) FROM user_actions WHERE action_type = 'suggestion' AND action_details = 'offershorter' AND DATE(timestamp AT TIME ZONE '{moscow_tz}') = CURRENT_DATE;"

    # New subscriptions today
    new_subs_query = f"SELECT COUNT(id) FROM user_schedule_subscriptions WHERE DATE(added_at AT TIME ZONE '{moscow_tz}') = CURRENT_DATE;"

    new_users_count = await db_conn.fetchval(new_users_query)
    total_actions_count = await db_conn.fetchval(total_actions_query)
    new_suggestions_count = await db_conn.fetchval(new_suggestions_query)
    new_subs_count = await db_conn.fetchval(new_subs_query)

    return {"new_users": new_users_count, "total_actions": total_actions_count, "new_subscriptions": new_subs_count, "new_suggestions": new_suggestions_count}

async def get_new_users_per_day_from_db(db_conn):
    """Calculates the number of new users per day based on their first action."""
    query = """
        WITH FirstActions AS (
            SELECT
                user_id,
                MIN(timestamp) as first_action_time
            FROM user_actions
            GROUP BY user_id
        )
        SELECT
            TO_CHAR(first_action_time AT TIME ZONE 'Europe/Moscow', 'YYYY-MM-DD') as registration_date,
            COUNT(user_id)::int as new_users_count
        FROM FirstActions
        GROUP BY registration_date
        ORDER BY registration_date ASC;
    """
    rows = await db_conn.fetch(query)
    return [{"date": row['registration_date'], "count": row['new_users_count']} for row in rows]

async def get_user_profile_data_from_db(
    db_conn,
    user_id: int,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = 'timestamp',
    sort_order: str = 'desc'
):
    """Извлекает детали профиля пользователя и пагинированный список его действий. Оптимизированная версия."""
    # --- Безопасная сортировка ---
    allowed_sort_columns = ['id', 'action_type', 'action_details', 'timestamp']
    if sort_by not in allowed_sort_columns:
        sort_by = 'timestamp'
    sort_order = 'ASC' if sort_order.lower() == 'asc' else 'DESC'

    # --- Шаг 1: Получаем детали пользователя и общее количество действий ---
    user_query = """
        SELECT
            user_id,
            full_name,
            COALESCE(username, 'Нет username') AS username,
            avatar_pic_url,
            (SELECT COUNT(*) FROM user_actions WHERE user_id = $1) as total_actions
        FROM users u
        WHERE user_id = $1;
    """
    user_details_row = await db_conn.fetchrow(user_query, user_id)

    if not user_details_row:
        return None # Пользователь не найден

    user_details = dict(user_details_row)
    total_actions = user_details["total_actions"]

    # --- Шаг 2: Получаем пагинированный список действий ---
    actions = []
    if total_actions > 0:
        actions_query = f"""
            SELECT
                id,
                action_type,
                action_details,
                TO_CHAR(timestamp AT TIME ZONE 'Europe/Moscow', 'YYYY-MM-DD HH24:MI:SS') AS timestamp
            FROM user_actions
            WHERE user_id = $1
            ORDER BY {sort_by} {sort_order}
            LIMIT $2 OFFSET $3;
        """
        offset = (page - 1) * page_size
        action_rows = await db_conn.fetch(actions_query, user_id, page_size, offset)
        actions = [dict(row) for row in action_rows]

    offset = (page - 1) * page_size

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

    # --- Safe sorting ---
    allowed_sort_columns = ['user_id', 'full_name', 'username']
    if sort_by not in allowed_sort_columns:
        sort_by = 'full_name'
    sort_order = 'DESC' if sort_order.lower() == 'desc' else 'ASC'
    order_by_clause = f"ORDER BY u.{sort_by} {sort_order}"

    # --- OPTIMIZED: Use a single query with a window function for the total count ---
    count_query = """
        SELECT COUNT(*) FROM (
            SELECT 1 FROM user_actions WHERE action_type = $1 AND action_details = $2 GROUP BY user_id
        ) as distinct_users;
    """
    total_users = await db_conn.fetchval(count_query, db_action_type, action_details)

    # --- OPTIMIZED: Use GROUP BY instead of DISTINCT for potentially better performance ---
    users_query = f"""
        SELECT
            u.user_id,
            u.full_name,
            COALESCE(u.username, 'Нет username') AS username
        FROM users u
        JOIN user_actions ua ON u.user_id = ua.user_id
        WHERE ua.action_type = $1 AND ua.action_details = $2
        GROUP BY u.user_id, u.full_name, u.username
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
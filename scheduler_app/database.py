import asyncpg
import logging
import datetime

from .config import DATABASE_URL

logger = logging.getLogger(__name__)

# Global connection pool
pool = None

async def init_db_pool():
    global pool
    if pool is None:
        try:
            pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=5)
            logger.info("Scheduler: Database connection pool created successfully.")
        except Exception as e:
            logger.error(f"Scheduler: Failed to create database connection pool: {e}", exc_info=True)
            raise

async def close_db_pool():
    global pool
    if pool:
        await pool.close()
        logger.info("Scheduler: Database connection pool closed.")

async def get_subscriptions_for_notification(notification_time: str) -> list:
    """Gets all active subscriptions for a specific time of day (HH:MM)."""
    if not pool:
        raise ConnectionError("Database pool is not initialized.")
    async with pool.acquire() as connection:
        rows = await connection.fetch("""
            SELECT user_id, entity_type, entity_id, entity_name
            FROM user_schedule_subscriptions
            WHERE is_active = TRUE AND TO_CHAR(notification_time, 'HH24:MI') = $1
        """, notification_time)
        return [dict(row) for row in rows]
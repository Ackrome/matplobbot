import asyncio
import aiosqlite
import asyncpg
import os
import logging
import json
from dotenv import load_dotenv

# --- Configuration ---

# Load environment variables from .env file
load_dotenv()

# Path to your old SQLite database file
SQLITE_DB_PATH = "./db_data/user_actions.db"

# PostgreSQL connection details (from your .env or docker-compose)
POSTGRES_USER = os.getenv("POSTGRES_USER", "user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost") # Use 'localhost' when running script outside Docker
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "matplobbot_db")

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def migrate_table(sqlite_conn, pg_pool, table_name, pg_columns, sqlite_columns=None):
    """Generic function to migrate data from a SQLite table to a PostgreSQL table."""
    if sqlite_columns is None:
        sqlite_columns = pg_columns

    logger.info(f"Starting migration for table: {table_name}...")
    
    try:
        # Read from SQLite
        async with sqlite_conn.execute(f"SELECT {', '.join(sqlite_columns)} FROM {table_name}") as cursor:
            rows = await cursor.fetchall()

        if not rows:
            logger.info(f"Table '{table_name}' is empty. Nothing to migrate.")
            return

        # Write to PostgreSQL
        async with pg_pool.acquire() as pg_conn:
            # Use copy_records_to_table for high performance bulk inserts
            await pg_conn.copy_records_to_table(
                table_name,
                records=rows,
                columns=pg_columns,
                timeout=60
            )
        
        logger.info(f"Successfully migrated {len(rows)} records to '{table_name}'.")

    except Exception as e:
        logger.error(f"Failed to migrate table '{table_name}': {e}", exc_info=True)
        raise

async def main():
    """Main migration logic."""
    
    # Check if SQLite DB exists
    if not os.path.exists(SQLITE_DB_PATH):
        logger.error(f"SQLite database not found at '{SQLITE_DB_PATH}'. Please make sure the path is correct and the file exists.")
        return

    pg_pool = None
    try:
        # Establish connections
        sqlite_conn = await aiosqlite.connect(SQLITE_DB_PATH)
        pg_pool = await asyncpg.create_pool(DATABASE_URL)

        logger.info("Successfully connected to both SQLite and PostgreSQL.")

        # --- Migration Steps ---

        # 1. Migrate 'users' table
        # Special handling for JSON 'settings' column
        logger.info("Migrating 'users' table with special handling for 'settings'...")
        async with sqlite_conn.execute("SELECT user_id, username, full_name, avatar_pic_url, settings, onboarding_completed FROM users") as cursor:
            user_rows = await cursor.fetchall()
        
        processed_user_rows = []
        for row in user_rows:
            # The 'settings' column is TEXT in SQLite and needs to be a valid JSON string for PostgreSQL's JSONB
            settings_str = row[4]
            try:
                # Validate and re-serialize to ensure it's valid JSON
                json.loads(settings_str)
                processed_user_rows.append(row)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Invalid JSON in settings for user_id {row[0]}. Defaulting to '{{}}'. Data: {settings_str}")
                # Replace invalid JSON with an empty JSON object string
                processed_user_rows.append(row[:4] + ('{}',) + row[5:])

        async with pg_pool.acquire() as pg_conn:
            await pg_conn.copy_records_to_table(
                'users',
                records=processed_user_rows,
                columns=('user_id', 'username', 'full_name', 'avatar_pic_url', 'settings', 'onboarding_completed')
            )
        logger.info(f"Successfully migrated {len(processed_user_rows)} records to 'users'.")


        # 2. Migrate other tables
        await migrate_table(sqlite_conn, pg_pool, 'user_actions', ['id', 'user_id', 'action_type', 'action_details', 'timestamp'])
        await migrate_table(sqlite_conn, pg_pool, 'user_favorites', ['id', 'user_id', 'code_path', 'added_at'])
        await migrate_table(sqlite_conn, pg_pool, 'latex_cache', ['formula_hash', 'image_url', 'created_at'])
        await migrate_table(sqlite_conn, pg_pool, 'user_github_repos', ['id', 'user_id', 'repo_path', 'added_at'])

        # --- Reset Sequences ---
        # After a bulk copy, PostgreSQL sequences are not updated. We must reset them manually.
        logger.info("Resetting primary key sequences in PostgreSQL...")
        async with pg_pool.acquire() as pg_conn:
            await pg_conn.execute("SELECT setval('user_actions_id_seq', (SELECT MAX(id) FROM user_actions));")
            await pg_conn.execute("SELECT setval('user_favorites_id_seq', (SELECT MAX(id) FROM user_favorites));")
            await pg_conn.execute("SELECT setval('user_github_repos_id_seq', (SELECT MAX(id) FROM user_github_repos));")
        logger.info("Sequences reset successfully.")

        logger.info("--- MIGRATION COMPLETED SUCCESSFULLY ---")

    except Exception as e:
        logger.error(f"--- MIGRATION FAILED: {e} ---", exc_info=True)
    finally:
        # Clean up connections
        if pg_pool:
            await pg_pool.close()
        if 'sqlite_conn' in locals() and sqlite_conn:
            await sqlite_conn.close()
        logger.info("Database connections closed.")

if __name__ == "__main__":
    asyncio.run(main())

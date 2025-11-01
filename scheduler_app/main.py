import asyncio
import logging
import os
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import aiohttp

# Load environment variables from .env file
load_dotenv()

from scheduler_app.config import LOG_DIR, SCHEDULER_LOG_FILE, BOT_TOKEN
from scheduler_app.database import init_db_pool, close_db_pool
from scheduler_app.jobs import send_daily_schedules

# We need to import this from the bot's services
from bot.services.university_api import create_ruz_api_client

# --- Logging Setup ---
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s",
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, SCHEDULER_LOG_FILE), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Starting Scheduler Service...")

    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN is not configured. Scheduler cannot send messages. Shutting down.")
        return

    await init_db_pool()

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        ruz_api_client_instance = create_ruz_api_client(session)

        scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
        scheduler.add_job(
            send_daily_schedules,
            trigger='cron',
            minute='*',  # Runs every minute
            kwargs={'http_session': session, 'ruz_api_client': ruz_api_client_instance}
        )
        scheduler.start()
        logger.info("Scheduler started. Waiting for jobs...")
        
        # Keep the service running indefinitely
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler service stopped.")
    finally:
        # This part is tricky to get right with async pools,
        # but for a clean shutdown, it's good practice.
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.run_until_complete(close_db_pool())
        else:
            asyncio.run(close_db_pool())
import asyncio
import logging
import os
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import aiohttp, aiohttp.web

# Load environment variables from .env file
load_dotenv()

from scheduler_app.config import LOG_DIR, SCHEDULER_LOG_FILE, BOT_TOKEN
from scheduler_app.jobs import send_daily_schedules, check_for_schedule_updates, prune_inactive_subscriptions, send_admin_summary, cleanup_old_log_files, update_schedule_cache
from shared_lib.database import init_db_pool, close_db_pool, get_db_connection_obj

# We need to import this from the bot's services
from shared_lib.services.university_api import create_ruz_api_client

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
    # Ensure the database schema is created before starting the scheduler
    logger.info("Database schema initialized by scheduler.")

    # Increase timeout for the scheduler, as pre-fetching all entities can be very slow.
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        ruz_api_client_instance = create_ruz_api_client(session)

        scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
        scheduler.add_job(
            send_daily_schedules,
            trigger='cron',
            minute='*',  # Runs every minute
            kwargs={'http_session': session, 'ruz_api_client': ruz_api_client_instance}
        )
        # Add the new change detection job to run every 2 hours
        scheduler.add_job(
            check_for_schedule_updates,
            trigger='interval',
            hours=2,
            kwargs={'http_session': session, 'ruz_api_client': ruz_api_client_instance}
        )
        # Add the new cache update job to run twice a day at 4 AM and 4 PM
        scheduler.add_job(
            update_schedule_cache,
            trigger='cron',
            hour='4,16',
            minute=0,
            kwargs={'http_session': session, 'ruz_api_client': ruz_api_client_instance}
        )
        
        # Add the new pruning job to run once a day (e.g., at 3 AM Moscow time)
        scheduler.add_job(
            prune_inactive_subscriptions,
            trigger='cron',
            hour=3, minute=0
        )

        # Add the new admin summary job to run every minute
        scheduler.add_job(
            send_admin_summary,
            trigger='cron',
            minute='*',
            kwargs={'http_session': session}
        )

        # Add the new log cleanup job to run once a day (e.g., at 4 AM Moscow time)
        scheduler.add_job(
            cleanup_old_log_files,
            trigger='cron',
            hour=4, minute=0,
            kwargs={'days_to_keep': 30}
        )
        # --- Health Check Server Setup ---
        async def health_check(request):
            try:
                db_ok = False
                async with get_db_connection_obj() as db:
                    await db.fetchval("SELECT 1")
                db_ok = True

                if scheduler.running and db_ok:
                    return aiohttp.web.json_response({"status": "ok", "scheduler": "running", "database": "connected"})
                else:
                    details = {"status": "unhealthy", "scheduler": "running" if scheduler.running else "stopped", "database": "connected" if db_ok else "disconnected"}
                    return aiohttp.web.json_response(details, status=503)
            except Exception as e:
                logger.error(f"Health check failed with an exception: {e}", exc_info=True)
                return aiohttp.web.json_response({"status": "error", "reason": str(e)}, status=500)

        health_app = aiohttp.web.Application()
        health_app.router.add_get("/health", health_check)
        runner = aiohttp.web.AppRunner(health_app)
        await runner.setup()
        site = aiohttp.web.TCPSite(runner, '0.0.0.0', 9584)
        await site.start()
        logger.info("Health check endpoint started at http://0.0.0.0:9584/health")

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
        if scheduler.running:
            scheduler.shutdown()
    finally:
        # This part is tricky to get right with async pools,
        # but for a clean shutdown, it's good practice.
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.run_until_complete(close_db_pool())
        else:
            asyncio.run(close_db_pool())
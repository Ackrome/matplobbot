import asyncio
import logging
import os

import aiohttp
import aiohttp.web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

# Load environment variables from .env before importing config modules that read os.getenv().
load_dotenv()

from scheduler_app.config import BOT_TOKEN, LOG_DIR, SCHEDULER_LOG_FILE, TELEGRAM_PROXY_URL
from scheduler_app.http_client import build_telegram_http_client_config
from scheduler_app.jobs import (
    check_for_schedule_updates,
    cleanup_old_log_files,
    prune_inactive_subscriptions,
    send_admin_summary,
    send_daily_schedules,
    update_schedule_cache,
)
from shared_lib.database import close_db_pool, get_session, init_db_pool
from shared_lib.request_context import configure_correlation_logging
from shared_lib.services.university_api import create_ruz_api_client

# --- Logging Setup ---
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [cid=%(correlation_id)s] - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, SCHEDULER_LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
configure_correlation_logging()
aps_logger = logging.getLogger("apscheduler")
aps_logger.propagate = True
if aps_logger.handlers:
    aps_logger.handlers.clear()

logger = logging.getLogger(__name__)


async def main():
    logger.info("Starting Scheduler Service...")

    if not BOT_TOKEN:
        logger.critical(
            "BOT_TOKEN is not configured. Scheduler cannot send messages. Shutting down."
        )
        return

    db_pool_initialized = False
    try:
        await init_db_pool()
        db_pool_initialized = True
        logger.info("Database schema initialized by scheduler.")

        # Increase timeout for scheduler tasks that can be slow on large datasets.
        timeout = aiohttp.ClientTimeout(total=120)
        telegram_session_kwargs, telegram_request_kwargs = build_telegram_http_client_config(
            timeout, TELEGRAM_PROXY_URL, log_context="scheduler Telegram session"
        )
        async with (
            aiohttp.ClientSession(timeout=timeout, trust_env=False) as ruz_session,
            aiohttp.ClientSession(**telegram_session_kwargs) as telegram_session,
        ):
            ruz_api_client_instance = create_ruz_api_client(ruz_session)
            scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

            scheduler.add_job(
                send_daily_schedules,
                trigger="cron",
                minute="*",
                kwargs={
                    "http_session": telegram_session,
                    "telegram_request_kwargs": telegram_request_kwargs,
                    "ruz_api_client": ruz_api_client_instance,
                },
            )
            scheduler.add_job(
                check_for_schedule_updates,
                trigger="interval",
                hours=2,
                kwargs={
                    "http_session": telegram_session,
                    "telegram_request_kwargs": telegram_request_kwargs,
                    "ruz_api_client": ruz_api_client_instance,
                },
            )
            scheduler.add_job(
                update_schedule_cache,
                trigger="cron",
                hour="4,16",
                minute=0,
                kwargs={
                    "http_session": telegram_session,
                    "ruz_api_client": ruz_api_client_instance,
                },
            )
            scheduler.add_job(
                prune_inactive_subscriptions,
                trigger="cron",
                hour=3,
                minute=0,
            )
            scheduler.add_job(
                send_admin_summary,
                trigger="cron",
                minute="*",
                kwargs={
                    "http_session": telegram_session,
                    "telegram_request_kwargs": telegram_request_kwargs,
                },
            )
            scheduler.add_job(
                cleanup_old_log_files,
                trigger="cron",
                hour=4,
                minute=0,
                kwargs={"days_to_keep": 30},
            )

            async def health_check(request):
                try:
                    async with get_session() as db_session:
                        from sqlalchemy import text

                        await db_session.execute(text("SELECT 1"))

                    if scheduler.running:
                        return aiohttp.web.json_response(
                            {"status": "ok", "scheduler": "running", "database": "connected"}
                        )

                    return aiohttp.web.json_response(
                        {"status": "unhealthy", "scheduler": "stopped", "database": "connected"},
                        status=503,
                    )
                except Exception as exc:
                    logger.error("Health check failed with an exception: %s", exc, exc_info=True)
                    return aiohttp.web.json_response(
                        {"status": "error", "reason": str(exc)}, status=500
                    )

            health_app = aiohttp.web.Application()
            health_app.router.add_get("/health", health_check)
            runner = aiohttp.web.AppRunner(health_app)
            runner_setup = False
            site = None

            try:
                await runner.setup()
                runner_setup = True
                site = aiohttp.web.TCPSite(runner, "0.0.0.0", 9584)
                await site.start()
                logger.info("Health check endpoint started at http://0.0.0.0:9584/health")

                scheduler.start()
                logger.info("Scheduler started. Waiting for jobs...")

                while True:
                    await asyncio.sleep(3600)
            finally:
                if scheduler.running:
                    scheduler.shutdown(wait=False)
                    logger.info("Scheduler stopped.")

                if site is not None:
                    await site.stop()

                if runner_setup:
                    await runner.cleanup()
                    logger.info("Health check server stopped.")
    finally:
        if db_pool_initialized:
            await close_db_pool()
            logger.info("Database pool closed.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler service stopped.")

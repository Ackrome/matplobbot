import asyncio
import logging
import time
from datetime import UTC, datetime

import aiohttp
import aiohttp.web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

# Load environment variables from .env before importing config modules that read os.getenv().
load_dotenv()

from scheduler_app.config import (
    BOT_TOKEN,
    CELERY_QUEUE_ALERT_THRESHOLD,
    SCHEDULE_OUTBOX_ALERT_AGE_SECONDS,
    TELEGRAM_PROXY_URL,
)
from scheduler_app.http_client import build_telegram_http_client_config
from scheduler_app.job_health import monitor_job
from scheduler_app.jobs import (
    check_for_schedule_updates,
    deliver_pending_schedule_change_notifications,
    prune_inactive_subscriptions,
    refresh_schedule_entity_ids,
    send_admin_summary,
    send_daily_schedules,
    update_schedule_cache,
)
from shared_lib.database import close_db_pool, get_session, init_db_pool
from shared_lib.logging_config import configure_logging
from shared_lib.operational_metrics import get_operational_snapshot
from shared_lib.product_metrics import purge_expired_product_events
from shared_lib.redis_client import redis_client
from shared_lib.schedule_outbox import get_schedule_outbox_health
from shared_lib.services.curriculum_service import process_curriculum_queue, refresh_due_curricula
from shared_lib.services.university_api import create_ruz_api_client

# --- Logging Setup ---
configure_logging("matplobbot-scheduler")
aps_logger = logging.getLogger("apscheduler")
aps_logger.propagate = True
if aps_logger.handlers:
    aps_logger.handlers.clear()

logger = logging.getLogger(__name__)
_STARTED_AT = time.monotonic()


async def build_scheduler_health(scheduler_running: bool) -> tuple[dict[str, object], int]:
    """Build the externally monitored scheduler/DB/Celery queue health signal."""
    async with get_session() as db_session:
        from sqlalchemy import text

        await db_session.execute(text("SELECT 1"))

    celery_queue_depth = int(await redis_client.client.llen("celery"))
    queue_backlogged = celery_queue_depth >= CELERY_QUEUE_ALERT_THRESHOLD
    operations = await get_operational_snapshot()
    outbox = await get_schedule_outbox_health()
    stale_jobs = [
        row["name"]
        for row in operations.get("operations", [])
        if row.get("stale_after_seconds")
        and (
            row["status"] in {"stale", "error"}
            or (
                row["status"] == "unknown"
                and time.monotonic() - _STARTED_AT > row["stale_after_seconds"]
            )
        )
    ]
    outbox_backlogged = outbox["oldest_pending_age_seconds"] >= SCHEDULE_OUTBOX_ALERT_AGE_SECONDS
    healthy = (
        scheduler_running
        and not queue_backlogged
        and not outbox_backlogged
        and not stale_jobs
        and operations["available"]
    )
    payload: dict[str, object] = {
        "status": "ok" if healthy else "unhealthy",
        "scheduler": "running" if scheduler_running else "stopped",
        "database": "connected",
        "celery_queue": "backlogged" if queue_backlogged else "ok",
        "celery_queue_depth": celery_queue_depth,
        "celery_queue_alert_threshold": CELERY_QUEUE_ALERT_THRESHOLD,
        "operations": operations,
        "stale_or_failed_jobs": stale_jobs,
        "schedule_outbox": outbox,
        "schedule_outbox_alert_age_seconds": SCHEDULE_OUTBOX_ALERT_AGE_SECONDS,
    }
    return payload, 200 if healthy else 503


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
            # The hourly tick consults persisted due dates; documents are fetched weekly
            # (or every 14 days), surviving restarts without resetting their cadence.
            scheduler.add_job(
                refresh_due_curricula,
                "interval",
                hours=1,
                kwargs={"http_session": ruz_session},
                id="curriculum_documents",
                max_instances=1,
                coalesce=True,
                next_run_time=datetime.now(UTC),
            )
            scheduler.add_job(
                process_curriculum_queue,
                "interval",
                minutes=1,
                id="curriculum_processing",
                max_instances=1,
                coalesce=True,
                next_run_time=datetime.now(UTC),
            )

            scheduler.add_job(
                monitor_job("daily_schedules", send_daily_schedules),
                trigger="cron",
                minute="*",
                kwargs={
                    "http_session": telegram_session,
                    "telegram_request_kwargs": telegram_request_kwargs,
                    "ruz_api_client": ruz_api_client_instance,
                },
            )
            scheduler.add_job(
                monitor_job("schedule_updates", check_for_schedule_updates),
                trigger="interval",
                hours=2,
                kwargs={
                    "http_session": telegram_session,
                    "telegram_request_kwargs": telegram_request_kwargs,
                    "ruz_api_client": ruz_api_client_instance,
                },
            )
            scheduler.add_job(
                monitor_job("outbox_delivery", deliver_pending_schedule_change_notifications),
                trigger="interval",
                minutes=1,
                kwargs={
                    "http_session": telegram_session,
                    "telegram_request_kwargs": telegram_request_kwargs,
                },
            )
            scheduler.add_job(
                refresh_schedule_entity_ids,
                trigger="cron",
                day_of_week="sun",
                hour=2,
                minute=30,
                kwargs={
                    "ruz_api_client": ruz_api_client_instance,
                },
            )
            scheduler.add_job(
                monitor_job("schedule_refresh", update_schedule_cache),
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
                purge_expired_product_events,
                trigger="cron",
                hour=3,
                minute=15,
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

            async def health_check(request):
                try:
                    payload, status_code = await build_scheduler_health(scheduler.running)
                    return aiohttp.web.json_response(payload, status=status_code)
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

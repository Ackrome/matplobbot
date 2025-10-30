import logging
from datetime import datetime, timedelta
from aiogram import Bot

from ..database import get_subscriptions_for_notification
from .university_api import RuzAPIClient
from .schedule_service import format_schedule
from ..i18n import translator

logger = logging.getLogger(__name__)

async def send_daily_schedules(bot: Bot, ruz_api_client: RuzAPIClient):
    """
    This job runs every minute, checks for subscriptions for the current time,
    and sends the schedule for the next day.
    """
    # We check for the next day's schedule.
    target_date = datetime.now() + timedelta(days=1)
    target_date_str = target_date.strftime("%Y.%m.%d")
    
    # Get current time in HH:MM format to match the database query
    current_time_str = datetime.now().strftime("%H:%M")
    logger.info(f"Scheduler job running for time: {current_time_str}")

    try:
        subscriptions = await get_subscriptions_for_notification(current_time_str)
        if not subscriptions:
            logger.info(f"No subscriptions found for {current_time_str}.")
            return

        logger.info(f"Found {len(subscriptions)} subscriptions to notify for {current_time_str}.")

        for sub in subscriptions:
            try:
                schedule_data = await ruz_api_client.get_schedule(
                    sub['entity_type'], sub['entity_id'], start=target_date_str, finish=target_date_str
                )
                
                lang = await translator.get_user_language(sub['user_id'])
                formatted_text = format_schedule(schedule_data, lang, sub['entity_name'])

                await bot.send_message(sub['user_id'], formatted_text, parse_mode="Markdown")
                logger.info(f"Sent daily schedule to user {sub['user_id']} for '{sub['entity_name']}'.")
            except Exception as e:
                logger.error(f"Failed to send schedule to user {sub['user_id']} for subscription {sub['id']}: {e}", exc_info=True)
    
    except Exception as e:
        logger.error(f"Critical error in send_daily_schedules job: {e}", exc_info=True)
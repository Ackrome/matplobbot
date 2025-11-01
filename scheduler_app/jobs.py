import logging
from datetime import datetime, timedelta
import aiohttp

from .database import get_subscriptions_for_notification
from .config import BOT_TOKEN

# We need to import these from the bot's services.
# In a real-world scenario, this might be a shared library.
from shared_lib.services.university_api import RuzAPIClient
from shared_lib.services.schedule_service import format_schedule
from shared_lib.i18n import translator

logger = logging.getLogger(__name__)

async def send_telegram_message(session: aiohttp.ClientSession, user_id: int, text: str):
    """Sends a message using a direct Telegram API call."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': user_id,
        'text': text,
        'parse_mode': 'Markdown'
    }
    async with session.post(url, json=payload) as response:
        if response.status != 200:
            logger.error(f"Failed to send message to user {user_id}. Status: {response.status}, Response: {await response.text()}")
        else:
            logger.info(f"Sent daily schedule to user {user_id}.")

async def send_daily_schedules(http_session: aiohttp.ClientSession, ruz_api_client: RuzAPIClient):
    """
    This job runs every minute, checks for subscriptions for the current time,
    and sends the schedule for the next day.
    """
    target_date = datetime.now() + timedelta(days=1)
    target_date_str = target_date.strftime("%Y.%m.%d")
    current_time_str = datetime.now().strftime("%H:%M")
    logger.info(f"Scheduler job running for time: {current_time_str}")

    try:
        subscriptions = await get_subscriptions_for_notification(current_time_str)
        if not subscriptions:
            return

        logger.info(f"Found {len(subscriptions)} subscriptions to notify for {current_time_str}.")

        for sub in subscriptions:
            try:
                schedule_data = await ruz_api_client.get_schedule(
                    sub['entity_type'], sub['entity_id'], start=target_date_str, finish=target_date_str
                )
                
                # We assume the user's language is stored and accessible.
                # For simplicity, we'll use the bot's i18n module directly.
                lang = await translator.get_user_language(sub['user_id'])
                formatted_text = format_schedule(schedule_data, lang, sub['entity_name'])

                await send_telegram_message(http_session, sub['user_id'], formatted_text)

            except Exception as e:
                logger.error(f"Failed to process and send schedule to user {sub['user_id']} for entity '{sub['entity_name']}': {e}", exc_info=True)
    
    except Exception as e:
        logger.error(f"Critical error in send_daily_schedules job: {e}", exc_info=True)
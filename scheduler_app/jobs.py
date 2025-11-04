import logging
from datetime import datetime, timedelta
import aiohttp
import json
import asyncio
import hashlib
from zoneinfo import ZoneInfo
from .config import BOT_TOKEN

# We need to import these from the bot's services.
# In a real-world scenario, this might be a shared library.
from shared_lib.services.university_api import RuzAPIClient
from shared_lib.services.schedule_service import format_schedule
from shared_lib.i18n import translator
from shared_lib.database import get_subscriptions_for_notification, update_subscription_hash, get_all_active_subscriptions
from shared_lib.redis_client import redis_client

logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_LIMIT = 4096

async def send_telegram_message(session: aiohttp.ClientSession, user_id: int, text: str):
    """Sends a message using a direct Telegram API call."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    if len(text) <= TELEGRAM_MESSAGE_LIMIT:
        # Message is short enough, send as is
        payload = {'chat_id': user_id, 'text': text, 'parse_mode': 'HTML'}
        async with session.post(url, json=payload) as response:
            if response.status != 200:
                logger.error(f"Failed to send message to user {user_id}. Status: {response.status}, Response: {await response.text()}")
            else:
                logger.info(f"Sent daily schedule to user {user_id}.")
    else:
        # Message is too long, split it into chunks
        logger.info(f"Message for user {user_id} is too long ({len(text)} chars). Splitting into chunks.")
        for i in range(0, len(text), TELEGRAM_MESSAGE_LIMIT):
            chunk = text[i:i + TELEGRAM_MESSAGE_LIMIT]
            payload = {'chat_id': user_id, 'text': chunk, 'parse_mode': 'HTML'}
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    logger.error(f"Failed to send chunk to user {user_id}. Status: {response.status}, Response: {await response.text()}")
                    # Stop sending chunks for this user if one fails
                    break
                await asyncio.sleep(0.1) # Small delay to avoid rate limiting
        logger.info(f"Finished sending all chunks to user {user_id}.")


async def send_daily_schedules(http_session: aiohttp.ClientSession, ruz_api_client: RuzAPIClient):
    """
    This job runs every minute, checks for subscriptions for the current time,
    and sends the schedule for the next day.
    """
    # Use timezone-aware datetime for Moscow
    moscow_tz = ZoneInfo("Europe/Moscow")
    now_in_moscow = datetime.now(moscow_tz)
    # The schedule should be for the next day
    start_date = now_in_moscow + timedelta(days=1)
    # The RUZ API is more reliable when fetching a range. We'll fetch the next 7 days.
    # The format_schedule function will correctly pick the first available day from the response.
    end_date = start_date + timedelta(days=0)
    start_date_str = start_date.strftime("%Y.%m.%d")
    end_date_str = end_date.strftime("%Y.%m.%d")
    current_time_str = now_in_moscow.strftime("%H:%M")
    logger.info(f"Scheduler job running for time: {current_time_str}")

    try:
        subscriptions = await get_subscriptions_for_notification(current_time_str)
        if not subscriptions:
            return

        logger.info(f"Found {len(subscriptions)} subscriptions to notify for {current_time_str}.")

        for sub in subscriptions:
            try:
                schedule_data = await ruz_api_client.get_schedule(
                    sub['entity_type'], sub['entity_id'], start=start_date_str, finish=end_date_str
                )

                # --- Change Detection Logic ---
                new_hash = hashlib.sha256(json.dumps(schedule_data, sort_keys=True).encode()).hexdigest()
                old_hash = sub.get('last_schedule_hash')
                has_changed = old_hash and new_hash != old_hash
                # --- End Change Detection ---
                
                # We assume the user's language is stored and accessible.
                # For simplicity, we'll use the bot's i18n module directly.
                lang = await translator.get_user_language(sub['user_id'])
                formatted_text = format_schedule(schedule_data, lang, sub['entity_name'], sub['entity_type'], start_date=start_date.date(), is_week_view=False)

                if has_changed:
                    logger.info(f"Schedule for subscription ID {sub['id']} ({sub['entity_name']}) has changed. Notifying user {sub['user_id']}.")
                    change_notification_text = translator.gettext(lang, "schedule_change_notification", entity_name=sub['entity_name'])
                    await send_telegram_message(http_session, sub['user_id'], change_notification_text)
                
                await send_telegram_message(http_session, sub['user_id'], formatted_text)

                # Update the hash in the database for the next check
                await update_subscription_hash(sub['id'], new_hash)
            except Exception as e:
                logger.error(f"Failed to process and send schedule to user {sub['user_id']} for entity '{sub['entity_name']}': {e}", exc_info=True)
    
    except Exception as e:
        logger.error(f"Critical error in send_daily_schedules job: {e}", exc_info=True)


async def check_for_schedule_updates(http_session: aiohttp.ClientSession, ruz_api_client: RuzAPIClient):
    """
    Periodically checks all active subscriptions for changes over a 3-week period.
    If a change is detected, notifies the user.
    """
    logger.info("Starting schedule change detection job...")
    moscow_tz = ZoneInfo("Europe/Moscow")
    start_date = datetime.now(moscow_tz)
    end_date = start_date + timedelta(weeks=3)
    start_date_str = start_date.strftime("%Y.%m.%d")
    end_date_str = end_date.strftime("%Y.%m.%d")

    try:
        all_subscriptions = await get_all_active_subscriptions()
        if not all_subscriptions:
            logger.info("Change detection job: No active subscriptions found.")
            return

        logger.info(f"Change detection job: Checking {len(all_subscriptions)} subscriptions.")

        for sub in all_subscriptions:
            try:
                schedule_data = await ruz_api_client.get_schedule(
                    sub['entity_type'], sub['entity_id'], start=start_date_str, finish=end_date_str
                )
                new_hash = hashlib.sha256(json.dumps(schedule_data, sort_keys=True).encode()).hexdigest()
                old_hash = sub.get('last_schedule_hash')

                # Notify only if there was a previous hash and it's different.
                if old_hash and new_hash != old_hash:
                    logger.info(f"Change detected for subscription ID {sub['id']} ({sub['entity_name']}). Notifying user {sub['user_id']}.")
                    lang = await translator.get_user_language(sub['user_id'])
                    change_notification_text = translator.gettext(lang, "schedule_change_notification", entity_name=sub['entity_name'])
                    await send_telegram_message(http_session, sub['user_id'], change_notification_text)
                    
                    # Also send the new schedule
                    formatted_text = format_schedule(schedule_data, lang, sub['entity_name'], sub['entity_type'], start_date=start_date.date(), is_week_view=True)
                    await send_telegram_message(http_session, sub['user_id'], formatted_text)

                await update_subscription_hash(sub['id'], new_hash)
            except Exception as e:
                logger.error(f"Change detection: Failed to process subscription ID {sub['id']} for user {sub['user_id']}: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Critical error in check_for_schedule_updates job: {e}", exc_info=True)
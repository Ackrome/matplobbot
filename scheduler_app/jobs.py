import logging
from datetime import datetime, timedelta
import aiohttp
import json
import asyncio
import hashlib, random
from zoneinfo import ZoneInfo
from .config import BOT_TOKEN

# We need to import these from the bot's services.
# In a real-world scenario, this might be a shared library.
from shared_lib.services.university_api import RuzAPIClient, RuzAPIError
from shared_lib.services.schedule_service import format_schedule, diff_schedules
from shared_lib.i18n import translator
from shared_lib.database import get_subscriptions_for_notification, update_subscription_hash, delete_old_inactive_subscriptions, get_unique_active_subscription_entities, get_subscriptions_for_entity
from shared_lib.redis_client import redis_client

logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_LIMIT = 4096


async def send_telegram_message(session: aiohttp.ClientSession, chat_id: int, text: str, message_thread_id: int | None = None):
    """Sends a message using a direct Telegram API call."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    if len(text) <= TELEGRAM_MESSAGE_LIMIT:
        # Message is short enough, send as is
        payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
        if message_thread_id:
            payload['message_thread_id'] = message_thread_id
        async with session.post(url, json=payload) as response:
            if response.status != 200:
                logger.error(f"Failed to send message to chat {chat_id}. Status: {response.status}, Response: {await response.text()}")
            else:
                logger.info(f"Sent daily schedule to chat {chat_id}.")
    else:
        # Message is too long, split it into chunks
        logger.info(f"Message for chat {chat_id} is too long ({len(text)} chars). Splitting into chunks.")
        for i in range(0, len(text), TELEGRAM_MESSAGE_LIMIT):
            chunk = text[i:i + TELEGRAM_MESSAGE_LIMIT]
            payload = {'chat_id': chat_id, 'text': chunk, 'parse_mode': 'HTML'}
            if message_thread_id:
                payload['message_thread_id'] = message_thread_id
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    logger.error(f"Failed to send chunk to chat {chat_id}. Status: {response.status}, Response: {await response.text()}")
                    # Stop sending chunks for this user if one fails
                    break
                await asyncio.sleep(0.1) # Small delay to avoid rate limiting
        logger.info(f"Finished sending all chunks to chat {chat_id}.")


async def send_daily_schedules(http_session: aiohttp.ClientSession, ruz_api_client: RuzAPIClient):
    """
    This job runs every minute, checks for subscriptions for the current time,
    and sends the schedule for the next day.
    """
    # Use timezone-aware datetime for Moscow
    moscow_tz = ZoneInfo("Europe/Moscow")
    now_in_moscow = datetime.now(moscow_tz)
    # The schedule should be for the next day
    target_date = now_in_moscow.date() + timedelta(days=1)
    start_date, end_date = target_date, target_date # Fetch for a single day
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
                logger.info(f"Processing subscription ID: {sub['id']} for chat {sub['chat_id']} and entity '{sub['entity_name']}'.")
                schedule_data = await ruz_api_client.get_schedule(
                    sub['entity_type'], sub['entity_id'], start=start_date_str, finish=end_date_str
                )

                # --- Change Detection & Diff Logic ---
                # This job does not perform change detection; it simply sends the schedule for the next day.
                # The check_for_schedule_updates job is responsible for diffs.
                # We will just format and send.

                lang = await translator.get_language(sub['user_id'], sub['chat_id'])
                recipient_chat_id = sub['chat_id']
                thread_id = sub.get('message_thread_id')

                # Always send the full schedule for the upcoming day.
                logger.debug(f"Sub ID {sub['id']}: Sending full schedule for {target_date.strftime('%Y-%m-%d')}.")
                formatted_text = format_schedule(schedule_data, lang, sub['entity_name'], sub['entity_type'], start_date=target_date, is_week_view=False)
                await send_telegram_message(http_session, recipient_chat_id, formatted_text, thread_id)

            except Exception as e:
                logger.error(f"Failed to process and send schedule to chat {sub.get('chat_id')} for entity '{sub['entity_name']}': {e}", exc_info=True)
    
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
        # 1. Fetch unique entities to avoid redundant API calls
        unique_entities = await get_unique_active_subscription_entities()
        if not unique_entities:
            logger.info("Change detection job: No unique active entities found.")
            return

        logger.info(f"Change detection job: Checking {len(unique_entities)} unique entities.")

        # 2. Loop through unique entities, not all subscriptions
        for entity in unique_entities:
            try:
                # Fetch schedule data ONCE per unique entity
                new_schedule_data = await ruz_api_client.get_schedule(
                    entity['entity_type'], entity['entity_id'], start=start_date_str, finish=end_date_str
                )
                new_hash = hashlib.sha256(json.dumps(new_schedule_data, sort_keys=True).encode()).hexdigest()

                # Get all subscriptions for this specific entity
                subscriptions_for_entity = await get_subscriptions_for_entity(entity['entity_type'], entity['entity_id'])

                # Use the first subscription's hash as a reference. They should all be the same for the same entity.
                # If not, this logic will self-correct on the next run.
                reference_hash = subscriptions_for_entity[0].get('last_schedule_hash') if subscriptions_for_entity else None

                if reference_hash and new_hash != reference_hash:
                    logger.info(f"Change detected for entity '{entity['entity_name']}'. Notifying {len(subscriptions_for_entity)} subscribers.")
                    # Fetch old data from Redis using the first subscription as a reference
                    ref_sub = subscriptions_for_entity[0]
                    redis_key = f"schedule_data:{ref_sub['id']}"
                    old_schedule_data_raw = await redis_client.get_user_cache(ref_sub['user_id'], redis_key)
                    old_schedule_data = json.loads(old_schedule_data_raw) if old_schedule_data_raw else None

                    # Notify all subscribers for this entity
                    for sub in subscriptions_for_entity:
                        lang = await translator.get_language(sub['user_id'], sub['chat_id'])
                        diff_text = diff_schedules(old_schedule_data, new_schedule_data, lang) if old_schedule_data else None
                        if diff_text:
                            header = translator.gettext(lang, "schedule_change_notification", entity_name=sub['entity_name'])
                            await send_telegram_message(http_session, sub['chat_id'], f"{header}\n\n{diff_text}", sub.get('message_thread_id'))

                # 3. Update state for ALL subscriptions of this entity
                for sub in subscriptions_for_entity:
                    await update_subscription_hash(sub['id'], new_hash)
                    await redis_client.set_user_cache(sub['user_id'], f"schedule_data:{sub['id']}", json.dumps(new_schedule_data), ttl=None)

                # 4. Stagger requests to avoid thundering herd
                await asyncio.sleep(1 + random.uniform(0.5, 1.5))

            except RuzAPIError as e: # Be more specific with API errors
                logger.warning(f"Change detection: RUZ API error for entity '{entity.get('entity_name')}': {e}")
            except Exception as e: # Catch other errors
                logger.error(f"Change detection: Failed to process entity '{entity.get('entity_name')}': {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Critical error in check_for_schedule_updates job: {e}", exc_info=True)


async def prune_inactive_subscriptions():
    """
    Periodically cleans up subscriptions that have been disabled for a long time (e.g., 30 days).
    """
    logger.info("Starting job to prune old, inactive subscriptions...")
    try:
        deleted_count = await delete_old_inactive_subscriptions(days_inactive=30)
        if deleted_count > 0:
            logger.info(f"Successfully pruned {deleted_count} old, inactive subscriptions from the database.")
    except Exception as e:
        logger.error(f"Critical error in prune_inactive_subscriptions job: {e}", exc_info=True)
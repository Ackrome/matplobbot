import logging
from datetime import date, datetime, timedelta
import aiohttp, collections
import json, os
import asyncio
import hashlib, random
from zoneinfo import ZoneInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from .config import BOT_TOKEN, LOG_DIR

# We need to import these from the bot's services.
from shared_lib.services.university_api import RuzAPIClient, RuzAPIError
from shared_lib.services.schedule_service import format_schedule, diff_schedules
from shared_lib.i18n import translator
from shared_lib.database import (
    get_subscriptions_for_notification, update_subscription_hash, 
    delete_old_inactive_subscriptions, get_all_active_subscriptions, 
    get_all_short_names, get_user_settings, get_admin_daily_summary,
    get_db_connection_obj
)
from shared_lib.redis_client import redis_client

logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_LIMIT = 4096


async def send_telegram_message(session: aiohttp.ClientSession, chat_id: int, text: str, message_thread_id: int | None = None, reply_markup: dict | None = None) -> dict | None:
    """
    Sends a message using a direct Telegram API call.
    Returns the JSON response result (containing message_id) on success, or None on failure.
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    # If text is too long and we have markup, we can't easily split it without losing markup on parts.
    # For admin summaries, text usually fits. For schedules, we might split.
    # If splitting is needed, reply_markup is usually only attached to the last part or handled differently.
    
    if len(text) <= TELEGRAM_MESSAGE_LIMIT:
        payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
        if message_thread_id:
            payload['message_thread_id'] = message_thread_id
        if reply_markup:
            payload['reply_markup'] = reply_markup

        async with session.post(url, json=payload) as response:
            if response.status != 200:
                logger.error(f"Failed to send message to chat {chat_id}. Status: {response.status}, Response: {await response.text()}")
                return None
            else:
                logger.info(f"Sent message to chat {chat_id}.")
                resp_json = await response.json()
                return resp_json.get('result')
    else:
        # Message is too long, split it into chunks. 
        # Note: reply_markup will be sent with the LAST chunk only to ensure it's at the bottom.
        logger.info(f"Message for chat {chat_id} is too long ({len(text)} chars). Splitting into chunks.")
        last_result = None
        for i in range(0, len(text), TELEGRAM_MESSAGE_LIMIT):
            chunk = text[i:i + TELEGRAM_MESSAGE_LIMIT]
            payload = {'chat_id': chat_id, 'text': chunk, 'parse_mode': 'HTML'}
            if message_thread_id:
                payload['message_thread_id'] = message_thread_id
            
            # Attach markup only to the last chunk
            if reply_markup and (i + TELEGRAM_MESSAGE_LIMIT >= len(text)):
                payload['reply_markup'] = reply_markup

            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    logger.error(f"Failed to send chunk to chat {chat_id}. Status: {response.status}, Response: {await response.text()}")
                    break
                
                resp_json = await response.json()
                last_result = resp_json.get('result')
                await asyncio.sleep(0.1) # Small delay
        
        logger.info(f"Finished sending all chunks to chat {chat_id}.")
        return last_result


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
    
    # Only log periodically or if subscriptions exist to reduce spam
    # logger.info(f"Scheduler job running for time: {current_time_str}")

    try:
        subscriptions = await get_subscriptions_for_notification(current_time_str)
        if not subscriptions:
            return

        # --- OPTIMIZATION: Group subscriptions by entity to avoid redundant API calls ---
        grouped_subscriptions = collections.defaultdict(list)
        for sub in subscriptions:
            entity_key = (sub['entity_type'], sub['entity_id'])
            grouped_subscriptions[entity_key].append(sub)

        logger.info(f"Found {len(subscriptions)} subscriptions across {len(grouped_subscriptions)} unique entities for {current_time_str}.")

        for entity_key, subs_for_entity in grouped_subscriptions.items():
            entity_type, entity_id = entity_key
            entity_name_for_log = subs_for_entity[0].get('entity_name', 'Unknown')
            
            try:
                # --- Fetch schedule data ONCE per unique entity ---
                logger.info(f"Fetching schedule for entity '{entity_name_for_log}' ({entity_type}:{entity_id}) for {len(subs_for_entity)} subscribers.")
                schedule_data = await ruz_api_client.get_schedule(
                    entity_type, entity_id, start=start_date_str, finish=end_date_str
                )

                # --- Process and send to all subscribers for this entity ---
                for sub in subs_for_entity:
                    try:
                        lang = await translator.get_language(sub['user_id'], sub['chat_id'])
                        recipient_chat_id = sub['chat_id']
                        thread_id = sub.get('message_thread_id')

                        formatted_text = await format_schedule(schedule_data, lang, sub['entity_name'], sub['entity_type'], sub['user_id'], start_date=target_date, is_week_view=False)
                        await send_telegram_message(http_session, recipient_chat_id, formatted_text, thread_id)
                        await asyncio.sleep(0.1)
                    except Exception as e:
                        logger.error(f"Failed to send to individual subscriber (sub_id: {sub['id']}, chat_id: {sub['chat_id']}): {e}", exc_info=True)

            except Exception as e:
                logger.error(f"Failed to process entity group '{entity_name_for_log}': {e}", exc_info=True)

    except Exception as e:
        logger.error(f"Critical error in send_daily_schedules job: {e}", exc_info=True)


async def check_for_schedule_updates(http_session: aiohttp.ClientSession, ruz_api_client: RuzAPIClient):
    """
    Periodically checks all active subscriptions for changes.
    """
    logger.info("Starting schedule change detection job...")
    
    moscow_tz = ZoneInfo("Europe/Moscow")
    today = datetime.now(moscow_tz).date()
    current_year = today.year

    if 2 <= today.month <= 6 or (today.month == 7 and today.day < 15):
        start_date = date(current_year, 2, 1)
        end_date = date(current_year, 7, 14)
    else:
        if today.month == 1:
            start_date = date(current_year - 1, 7, 15)
            end_date = date(current_year, 1, 31)
        else:
            start_date = date(current_year, 7, 15)
            end_date = date(current_year + 1, 1, 31)

    start_date_str = start_date.strftime("%Y.%m.%d")
    end_date_str = end_date.strftime("%Y.%m.%d")

    try:
        all_subscriptions = await get_all_active_subscriptions()
        if not all_subscriptions:
            return

        grouped_subscriptions = collections.defaultdict(list)
        for sub in all_subscriptions:
            entity_key = (sub['entity_type'], sub['entity_id'])
            grouped_subscriptions[entity_key].append(sub)

        short_names_map = await get_all_short_names()

        for entity_key, subs_for_entity in grouped_subscriptions.items():
            entity_type, entity_id = entity_key
            entity_name = subs_for_entity[0]['entity_name']

            try:
                new_schedule_data = await ruz_api_client.get_schedule(
                    entity_type, entity_id, start=start_date_str, finish=end_date_str
                )
                new_hash = hashlib.sha256(json.dumps(new_schedule_data, sort_keys=True).encode()).hexdigest()

                reference_hash = subs_for_entity[0].get('last_schedule_hash')

                if reference_hash and new_hash != reference_hash:
                    logger.info(f"Change detected for entity '{entity_name}'.")
                    ref_sub = subs_for_entity[0]
                    redis_key = f"schedule_data:{ref_sub['id']}"
                    old_schedule_data_raw = await redis_client.get_user_cache(ref_sub['user_id'], redis_key)
                    old_schedule_data = json.loads(old_schedule_data_raw) if old_schedule_data_raw else None

                    diffs_by_lang = {}

                    for sub in subs_for_entity:
                        lang = await translator.get_language(sub['user_id'], sub['chat_id'])
                        if lang not in diffs_by_lang:
                            if old_schedule_data:
                                diffs_by_lang[lang] = diff_schedules(old_schedule_data, new_schedule_data, lang, use_short_names=True, short_names_map=short_names_map)
                            else:
                                diffs_by_lang[lang] = None
                        
                        if diffs_by_lang[lang]:
                            header = translator.gettext(lang, "schedule_change_notification", entity_name=sub['entity_name'])
                            await send_telegram_message(http_session, sub['chat_id'], f"{header}\n\n{diffs_by_lang[lang]}", sub.get('message_thread_id'))

                for sub in subs_for_entity:
                    await update_subscription_hash(sub['id'], new_hash)
                    await redis_client.set_user_cache(sub['user_id'], f"schedule_data:{sub['id']}", json.dumps(new_schedule_data), ttl=None)

                await asyncio.sleep(1 + random.uniform(0.5, 1.5))

            except RuzAPIError as e:
                logger.warning(f"Change detection: RUZ API error for entity '{entity_name}': {e}")
            except Exception as e:
                logger.error(f"Change detection: Failed to process entity '{entity_name}': {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Critical error in check_for_schedule_updates job: {e}", exc_info=True)


async def prune_inactive_subscriptions():
    """
    Periodically cleans up subscriptions that have been disabled for a long time.
    """
    logger.info("Starting job to prune old, inactive subscriptions...")
    try:
        deleted_count = await delete_old_inactive_subscriptions(days_inactive=30)
        if deleted_count > 0:
            logger.info(f"Successfully pruned {deleted_count} old, inactive subscriptions.")
    except Exception as e:
        logger.error(f"Critical error in prune_inactive_subscriptions job: {e}", exc_info=True)

async def cleanup_old_log_files(days_to_keep: int = 30):
    """
    Periodically cleans up old log files.
    """
    logger.info(f"Starting job to clean up log files older than {days_to_keep} days...")
    try:
        now = datetime.now()
        cutoff = now - timedelta(days=days_to_keep)
        
        if not os.path.exists(LOG_DIR):
            return

        deleted_count = 0
        for filename in os.listdir(LOG_DIR):
            file_path = os.path.join(LOG_DIR, filename)
            if os.path.isfile(file_path) and filename.endswith('.log'):
                try:
                    file_mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if file_mod_time < cutoff:
                        os.remove(file_path)
                        logger.info(f"Deleted old log file: {file_path}")
                        deleted_count += 1
                except Exception as e:
                    logger.error(f"Error processing log file {file_path}: {e}")
        logger.info(f"Log cleanup finished. Deleted {deleted_count} old log files.")
    except Exception as e:
        logger.error(f"Critical error in cleanup_old_log_files job: {e}", exc_info=True)

async def send_admin_summary(http_session: aiohttp.ClientSession):
    """
    Runs every minute, checks if it's time to send a daily summary to admins.
    Generates the summary directly instead of triggering a command via text.
    """
    from .config import ADMIN_USER_IDS
    if not ADMIN_USER_IDS:
        return

    moscow_tz = ZoneInfo("Europe/Moscow")
    current_time_str = datetime.now(moscow_tz).strftime("%H:%M")
    current_weekday = datetime.now(moscow_tz).weekday()

    for admin_id in ADMIN_USER_IDS:
        try:
            settings = await get_user_settings(admin_id)
            summary_time = settings.get('admin_daily_summary_time', '09:00')
            summary_days = settings.get('admin_summary_days', [0, 1, 2, 3, 4])

            if summary_time == current_time_str and current_weekday in summary_days:
                logger.info(f"Time match for admin {admin_id}. Sending daily summary.")
                lang = await translator.get_language(admin_id)
                
                # --- 1. Build the Main Summary Text ---
                summary_parts = []
                try:
                    async with get_db_connection_obj() as db:
                        summary_data = await get_admin_daily_summary(db)
                    summary_parts.append(translator.gettext(lang, "admin_daily_summary_text", **summary_data))
                except Exception as e:
                    logger.error(f"Failed to get stats for admin summary: {e}", exc_info=True)
                    summary_parts.append("❌ Не удалось загрузить статистику.")

                # Send the main summary message (no buttons usually needed here)
                await send_telegram_message(http_session, admin_id, "\n".join(summary_parts))

                # --- 2. Handle Pending Suggestions (With Buttons) ---
                try:
                    pending_offers_raw = await redis_client.client.lrange('pending_shorter_offers', 0, -1)
                    if pending_offers_raw:
                        header_text = "\n\n" + translator.gettext(lang, "admin_summary_pending_offers_header")
                        await send_telegram_message(http_session, admin_id, header_text)
                        
                        for offer_raw in pending_offers_raw:
                            offer = json.loads(offer_raw)
                            notification_text = translator.gettext(
                                lang, "shorter_name_admin_notification",
                                user_id=offer['user_id'], user_name=offer['user_name'],
                                full_name=offer['full_name'], short_name=offer['short_name']
                            )
                            
                            data_to_hash = f"{offer['user_id']}:{offer['full_name']}:{offer['short_name']}"
                            data_hash = hashlib.sha1(data_to_hash.encode()).hexdigest()[:24]
                            
                            # Manually construct the Inline Keyboard JSON for raw HTTP API
                            reply_markup = {
                                "inline_keyboard": [
                                    [
                                        {"text": "✅ Одобрить", "callback_data": f"shorter_name_admin:approve:{data_hash}"},
                                        {"text": "❌ Отклонить", "callback_data": f"shorter_name_admin:decline:{data_hash}"}
                                    ]
                                ]
                            }

                            # Send the message and capture result to get message_id
                            msg_result = await send_telegram_message(http_session, admin_id, notification_text, reply_markup=reply_markup)
                            
                            if msg_result:
                                # --- CRITICAL: Populate Cache for Bot's Callback Handler ---
                                # The bot handler expects the data to be in Redis to verify the hash and edit the message.
                                redis_key = f"suggestion_cache:{data_hash}"
                                payload_to_cache = {
                                    'data': data_to_hash,
                                    'user_name': offer['user_name'],
                                    'messages': [{'chat_id': admin_id, 'message_id': msg_result['message_id']}]
                                }
                                await redis_client.set_cache(redis_key, payload_to_cache, ttl=604800) # 7 days

                except Exception as e:
                    logger.error(f"Failed to process pending offers in scheduler: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Failed to process daily summary loop for admin {admin_id}: {e}", exc_info=True)
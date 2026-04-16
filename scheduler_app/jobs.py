import asyncio
import collections
import hashlib
import json
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp

from shared_lib.database import (
    batch_update_subscription_hashes,
    delete_old_inactive_subscriptions,
    get_admin_daily_summary,
    get_all_active_subscriptions,
    get_all_short_names,
    get_session,
    get_subscriptions_for_notification,
    get_unique_active_subscription_entities,
    get_user_settings,
    upsert_cached_schedule,
)
from shared_lib.i18n import translator
from shared_lib.redis_client import redis_client
from shared_lib.request_context import generate_correlation_id, set_correlation_id
from shared_lib.services.schedule_service import diff_schedules, format_schedule

# We need to import these from the bot's services.
from shared_lib.services.university_api import RuzAPIClient, RuzAPIError

from .config import BOT_TOKEN

logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_LIMIT = 4096


async def send_telegram_message(
    session: aiohttp.ClientSession,
    chat_id: int,
    text: str,
    message_thread_id: int | None = None,
    reply_markup: dict | None = None,
    request_kwargs: dict | None = None,
) -> dict | None:
    """
    Sends a message using a direct Telegram API call.
    Returns the JSON response result (containing message_id) on success, or None on failure.
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    request_kwargs = request_kwargs or {}

    async def post_payload(payload: dict) -> dict | None:
        try:
            async with session.post(url, json=payload, **request_kwargs) as response:
                if response.status != 200:
                    logger.error(
                        f"Failed to send message to chat {chat_id}. Status: {response.status}, Response: {await response.text()}"
                    )
                    return None

                resp_json = await response.json()
                logger.info(f"Sent message to chat {chat_id}.")
                return resp_json.get("result")
        except (TimeoutError, aiohttp.ClientError) as exc:
            logger.error(
                "Transport error while sending message to chat %s: %s",
                chat_id,
                exc,
                exc_info=True,
            )
            return None

    if len(text) <= TELEGRAM_MESSAGE_LIMIT:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if message_thread_id:
            payload["message_thread_id"] = message_thread_id
        if reply_markup:
            payload["reply_markup"] = reply_markup

        return await post_payload(payload)

    logger.info(
        f"Message for chat {chat_id} is too long ({len(text)} chars). Splitting into chunks."
    )
    last_result = None
    for i in range(0, len(text), TELEGRAM_MESSAGE_LIMIT):
        chunk = text[i : i + TELEGRAM_MESSAGE_LIMIT]
        payload = {"chat_id": chat_id, "text": chunk, "parse_mode": "HTML"}
        if message_thread_id:
            payload["message_thread_id"] = message_thread_id

        if reply_markup and (i + TELEGRAM_MESSAGE_LIMIT >= len(text)):
            payload["reply_markup"] = reply_markup

        last_result = await post_payload(payload)
        if last_result is None:
            break

        await asyncio.sleep(0.1)

    logger.info(f"Finished sending all chunks to chat {chat_id}.")
    return last_result


async def send_daily_schedules(
    http_session: aiohttp.ClientSession,
    ruz_api_client: RuzAPIClient,
    telegram_request_kwargs: dict | None = None,
):
    """
    This job runs every minute, checks for subscriptions for the current time,
    and sends the schedule for the next day.
    """
    correlation_id = generate_correlation_id(prefix="sched-daily")
    set_correlation_id(correlation_id)
    logger.info("Starting daily schedules job (cid=%s).", correlation_id)

    # Use timezone-aware datetime for Moscow
    moscow_tz = ZoneInfo("Europe/Moscow")
    now_in_moscow = datetime.now(moscow_tz)
    # The schedule should be for the next day
    target_date = now_in_moscow.date() + timedelta(days=1)
    start_date, end_date = target_date, target_date  # Fetch for a single day
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")
    current_time_str = now_in_moscow.strftime("%H:%M")

    subscriptions = await get_subscriptions_for_notification(current_time_str)
    if not subscriptions:
        return
    grouped_subscriptions = collections.defaultdict(list)
    for sub in subscriptions:
        entity_key = (sub["entity_type"], sub["entity_id"])
        grouped_subscriptions[entity_key].append(sub)

    logger.info(
        "Found %s subscriptions across %s unique entities for %s (cid=%s).",
        len(subscriptions),
        len(grouped_subscriptions),
        current_time_str,
        correlation_id,
    )

    entity_fetch_successes = 0
    entity_fetch_failures = 0
    subscriber_attempts = 0
    delivery_successes = 0
    delivery_failures = 0

    for entity_key, subs_for_entity in grouped_subscriptions.items():
        entity_type, entity_id = entity_key
        entity_name_for_log = subs_for_entity[0].get("entity_name", "Unknown")

        try:
            logger.info(
                "Fetching schedule for entity '%s' (%s:%s) for %s subscribers (cid=%s).",
                entity_name_for_log,
                entity_type,
                entity_id,
                len(subs_for_entity),
                correlation_id,
            )
            schedule_data = await ruz_api_client.get_schedule(
                entity_type, entity_id, start=start_date_str, finish=end_date_str
            )
            entity_fetch_successes += 1

            for sub in subs_for_entity:
                subscriber_attempts += 1
                try:
                    lang = await translator.get_language(sub["user_id"], sub["chat_id"])
                    recipient_chat_id = sub["chat_id"]
                    thread_id = sub.get("message_thread_id")

                    formatted_text = await format_schedule(
                        schedule_data,
                        lang,
                        sub["entity_name"],
                        sub["entity_type"],
                        sub["user_id"],
                        start_date=target_date,
                        is_week_view=False,
                        subscription_id=sub["id"],
                    )
                    send_result = await send_telegram_message(
                        http_session,
                        recipient_chat_id,
                        formatted_text,
                        thread_id,
                        request_kwargs=telegram_request_kwargs,
                    )
                    if send_result is None:
                        delivery_failures += 1
                    else:
                        delivery_successes += 1
                    await asyncio.sleep(0.1)
                except Exception as e:
                    delivery_failures += 1
                    logger.error(
                        "Failed to send to individual subscriber (sub_id: %s, chat_id: %s, cid=%s): %s",
                        sub["id"],
                        sub["chat_id"],
                        correlation_id,
                        e,
                        exc_info=True,
                    )

        except Exception as e:
            entity_fetch_failures += 1
            logger.error(
                "Failed to process entity group '%s' (cid=%s): %s",
                entity_name_for_log,
                correlation_id,
                e,
                exc_info=True,
            )

    logger.info(
        "Daily schedules job finished (cid=%s). Entity fetches: %s succeeded, %s failed. Deliveries: %s attempted, %s succeeded, %s failed.",
        correlation_id,
        entity_fetch_successes,
        entity_fetch_failures,
        subscriber_attempts,
        delivery_successes,
        delivery_failures,
    )

    if (
        subscriber_attempts > 0
        and delivery_successes == 0
        and delivery_failures == subscriber_attempts
    ):
        raise RuntimeError("Daily schedules job failed: every attempted delivery failed.")

    if (
        grouped_subscriptions
        and entity_fetch_successes == 0
        and entity_fetch_failures == len(grouped_subscriptions)
    ):
        raise RuntimeError("Daily schedules job failed: could not fetch any schedule data.")


# ... existing imports
from shared_lib.database import get_cached_schedule  # <--- Добавлен импорт

# ... existing imports

# ... (функция send_telegram_message и send_daily_schedules без изменений) ...


async def check_for_schedule_updates(
    http_session: aiohttp.ClientSession,
    ruz_api_client: RuzAPIClient,
    telegram_request_kwargs: dict | None = None,
):
    """
    Periodically checks all active subscriptions for changes.
    Optimized to prevent duplicate notifications by updating DB state immediately.
    """
    logger.info("Starting schedule change detection job...")

    moscow_tz = ZoneInfo("Europe/Moscow")
    today = datetime.now(moscow_tz).date()
    current_year = today.year

    # Определяем границы семестра для проверки изменений
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

    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    try:
        all_subscriptions = await get_all_active_subscriptions()
        if not all_subscriptions:
            return

        # Группируем подписки по сущностям (Group/Teacher/Auditorium)
        grouped_subscriptions = collections.defaultdict(list)
        for sub in all_subscriptions:
            entity_key = (sub["entity_type"], sub["entity_id"])
            grouped_subscriptions[entity_key].append(sub)

        short_names_map = await get_all_short_names()

        for entity_key, subs_for_entity in grouped_subscriptions.items():
            entity_type, entity_id = entity_key
            entity_name = subs_for_entity[0]["entity_name"]

            try:
                # 1. Получаем новое расписание из API
                new_schedule_data = await ruz_api_client.get_schedule(
                    entity_type, entity_id, start=start_date_str, finish=end_date_str
                )

                # Считаем хэш
                new_hash = hashlib.sha256(
                    json.dumps(new_schedule_data, sort_keys=True).encode()
                ).hexdigest()

                # Берем хэш любого подписчика этой группы (они должны быть одинаковы, если синхронизированы)
                # Если у кого-то рассинхрон, это исправится при массовом обновлении
                reference_hash = subs_for_entity[0].get("last_schedule_hash")

                if reference_hash and new_hash != reference_hash:
                    logger.info(
                        f"Change detected for entity '{entity_name}' ({entity_type}:{entity_id})."
                    )

                    # 2. Получаем СТАРЫЕ данные из БД (CachedSchedule) для сравнения
                    # Важно сделать это ДО обновления кэша
                    old_schedule_data = await get_cached_schedule(entity_type, entity_id)

                    # 3. IMPORTANT: immediately update DB state (cache + subscription hashes)
                    # Это предотвращает повторную обработку этой сущности, если отправка сообщений упадет.
                    await upsert_cached_schedule(entity_type, entity_id, new_schedule_data)
                    await batch_update_subscription_hashes(entity_type, entity_id, new_hash)

                    # Также обновляем Redis для совместимости (необязательно, но полезно)
                    # Обновляем для одного "референсного" пользователя, чтобы не спамить Redis запросами в цикле
                    # (В будущем логику redis_client.set_user_cache можно убрать, если перешли на CachedSchedule)
                    # await redis_client.set_cache(f"schedule_data:{entity_type}:{entity_id}", json.dumps(new_schedule_data))

                    # 4. Генерируем Diff и отправляем уведомления
                    if old_schedule_data:
                        # Diff генерируется один раз на язык, чтобы не пересчитывать N раз
                        diffs_by_lang = {}

                        for sub in subs_for_entity:
                            try:
                                lang = await translator.get_language(sub["user_id"], sub["chat_id"])
                                if lang not in diffs_by_lang:
                                    diff_text = diff_schedules(
                                        old_schedule_data,
                                        new_schedule_data,
                                        lang,
                                        use_short_names=True,
                                        short_names_map=short_names_map,
                                    )
                                    diffs_by_lang[lang] = diff_text

                                if diffs_by_lang[lang]:
                                    header = translator.gettext(
                                        lang,
                                        "schedule_change_notification",
                                        entity_name=sub["entity_name"],
                                    )
                                    await send_telegram_message(
                                        http_session,
                                        sub["chat_id"],
                                        f"{header}\n\n{diffs_by_lang[lang]}",
                                        sub.get("message_thread_id"),
                                        request_kwargs=telegram_request_kwargs,
                                    )
                            except Exception as inner_e:
                                logger.error(
                                    f"Failed to send update notification to chat {sub['chat_id']}: {inner_e}"
                                )
                    else:
                        logger.info(
                            f"Old schedule not found in cache for '{entity_name}'. Skipping diff notification, but updating hash."
                        )

                elif not reference_hash:
                    # Если хэша нет (первый запуск для этой подписки), просто сохраняем текущий
                    await batch_update_subscription_hashes(entity_type, entity_id, new_hash)
                    await upsert_cached_schedule(entity_type, entity_id, new_schedule_data)

                # Небольшая пауза между сущностями, чтобы не грузить API/БД пиками
                await asyncio.sleep(0.5)

            except RuzAPIError as e:
                logger.warning(f"Change detection: RUZ API error for entity '{entity_name}': {e}")
            except Exception as e:
                logger.error(
                    f"Change detection: Failed to process entity '{entity_name}': {e}",
                    exc_info=True,
                )
    except Exception as e:
        logger.error(f"Critical error in check_for_schedule_updates job: {e}", exc_info=True)


async def update_schedule_cache(http_session: aiohttp.ClientSession, ruz_api_client: RuzAPIClient):
    """
    Job to update the cached schedules in the database.
    Fetching the full semester schedule for all active subscriptions.
    """
    logger.info("Starting schedule cache update job...")

    moscow_tz = ZoneInfo("Europe/Moscow")
    today = datetime.now(moscow_tz).date()
    current_year = today.year

    # Determine semester range
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

    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    try:
        unique_entities = await get_unique_active_subscription_entities()
        if not unique_entities:
            logger.info("No active subscriptions to cache.")
            return

        logger.info(f"Updating cache for {len(unique_entities)} unique entities...")

        for entity in unique_entities:
            entity_type = entity["entity_type"]
            entity_id = entity["entity_id"]
            entity_name = entity["entity_name"]

            try:
                # Fetch full semester schedule
                schedule_data = await ruz_api_client.get_schedule(
                    entity_type, entity_id, start=start_date_str, finish=end_date_str
                )

                # Update DB
                await upsert_cached_schedule(entity_type, entity_id, schedule_data)
                logger.debug(f"Updated cache for {entity_name} ({entity_type}:{entity_id})")

                # Polite delay
                await asyncio.sleep(0.5)

            except RuzAPIError as e:
                logger.warning(f"Cache update failed for {entity_name}: {e}")
            except Exception as e:
                logger.error(f"Error caching schedule for {entity_name}: {e}", exc_info=True)

        logger.info("Schedule cache update job finished.")

    except Exception as e:
        logger.error(f"Critical error in update_schedule_cache job: {e}", exc_info=True)


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


async def send_admin_summary(
    http_session: aiohttp.ClientSession,
    telegram_request_kwargs: dict | None = None,
):
    """
    Runs every minute, checks if it's time to send a daily summary to admins.
    Generates the summary directly instead of triggering a command via text.
    """
    correlation_id = generate_correlation_id(prefix="sched-admin")
    set_correlation_id(correlation_id)
    logger.info("Starting admin summary job (cid=%s).", correlation_id)

    from .config import ADMIN_USER_IDS

    if not ADMIN_USER_IDS:
        return

    moscow_tz = ZoneInfo("Europe/Moscow")
    current_time_str = datetime.now(moscow_tz).strftime("%H:%M")
    current_weekday = datetime.now(moscow_tz).weekday()
    matched_admins = 0
    send_attempts = 0
    send_successes = 0
    send_failures = 0

    for admin_id in ADMIN_USER_IDS:
        try:
            settings = await get_user_settings(admin_id)
            summary_time = settings.get("admin_daily_summary_time", "09:00")
            summary_days = settings.get("admin_summary_days", [0, 1, 2, 3, 4])

            if summary_time == current_time_str and current_weekday in summary_days:
                matched_admins += 1
                logger.info(
                    "Time match for admin %s. Sending daily summary (cid=%s).",
                    admin_id,
                    correlation_id,
                )
                lang = await translator.get_language(admin_id)

                # --- 1. Build the Main Summary Text ---
                summary_parts = []
                try:
                    # IMPORTANT: use get_session() to acquire an SQLAlchemy session
                    async with get_session() as db:
                        summary_data = await get_admin_daily_summary(db)
                    summary_parts.append(
                        translator.gettext(lang, "admin_daily_summary_text", **summary_data)
                    )
                except Exception as e:
                    logger.error(f"Failed to get stats for admin summary: {e}", exc_info=True)
                    summary_parts.append("❌ Не удалось загрузить статистику.")

                # Send the main summary message (no buttons usually needed here)
                send_attempts += 1
                summary_result = await send_telegram_message(
                    http_session,
                    admin_id,
                    "\n".join(summary_parts),
                    request_kwargs=telegram_request_kwargs,
                )
                if summary_result is None:
                    send_failures += 1
                else:
                    send_successes += 1

                # --- 2. Handle Pending Suggestions (With Buttons) ---
                try:
                    pending_offers_raw = await redis_client.client.lrange(
                        "pending_shorter_offers", 0, -1
                    )
                    if pending_offers_raw:
                        header_text = "\n\n" + translator.gettext(
                            lang, "admin_summary_pending_offers_header"
                        )
                        send_attempts += 1
                        header_result = await send_telegram_message(
                            http_session,
                            admin_id,
                            header_text,
                            request_kwargs=telegram_request_kwargs,
                        )
                        if header_result is None:
                            send_failures += 1
                        else:
                            send_successes += 1

                        for offer_raw in pending_offers_raw:
                            offer = json.loads(offer_raw)
                            notification_text = translator.gettext(
                                lang,
                                "shorter_name_admin_notification",
                                user_id=offer["user_id"],
                                user_name=offer["user_name"],
                                full_name=offer["full_name"],
                                short_name=offer["short_name"],
                            )

                            data_to_hash = (
                                f"{offer['user_id']}:{offer['full_name']}:{offer['short_name']}"
                            )
                            data_hash = hashlib.sha1(data_to_hash.encode()).hexdigest()[:24]

                            # Manually construct the Inline Keyboard JSON for raw HTTP API
                            reply_markup = {
                                "inline_keyboard": [
                                    [
                                        {
                                            "text": "✅ Одобрить",
                                            "callback_data": f"shorter_name_admin:approve:{data_hash}",
                                        },
                                        {
                                            "text": "❌ Отклонить",
                                            "callback_data": f"shorter_name_admin:decline:{data_hash}",
                                        },
                                    ]
                                ]
                            }

                            # Send the message and capture result to get message_id
                            send_attempts += 1
                            msg_result = await send_telegram_message(
                                http_session,
                                admin_id,
                                notification_text,
                                reply_markup=reply_markup,
                                request_kwargs=telegram_request_kwargs,
                            )

                            if msg_result:
                                send_successes += 1
                                # --- CRITICAL: Populate Cache for Bot's Callback Handler ---
                                # The bot handler expects the data to be in Redis to verify the hash and edit the message.
                                redis_key = f"suggestion_cache:{data_hash}"
                                payload_to_cache = {
                                    "data": data_to_hash,
                                    "user_name": offer["user_name"],
                                    "messages": [
                                        {
                                            "chat_id": admin_id,
                                            "message_id": msg_result["message_id"],
                                        }
                                    ],
                                }
                                await redis_client.set_cache(
                                    redis_key, payload_to_cache, ttl=604800
                                )  # 7 days
                            else:
                                send_failures += 1

                except Exception as e:
                    logger.error(
                        "Failed to process pending offers in scheduler (cid=%s): %s",
                        correlation_id,
                        e,
                        exc_info=True,
                    )

        except Exception as e:
            logger.error(
                "Failed to process daily summary loop for admin %s (cid=%s): %s",
                admin_id,
                correlation_id,
                e,
                exc_info=True,
            )

    if matched_admins:
        logger.info(
            "Admin summary job finished (cid=%s). Matched admins: %s. Deliveries: %s attempted, %s succeeded, %s failed.",
            correlation_id,
            matched_admins,
            send_attempts,
            send_successes,
            send_failures,
        )

    if matched_admins > 0 and send_successes == 0 and send_failures > 0:
        raise RuntimeError("Admin summary job failed: every attempted delivery failed.")

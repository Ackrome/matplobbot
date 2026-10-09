import asyncio
import collections
import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import aiohttp

from shared_lib.database import (
    batch_update_subscription_hashes,
    delete_old_inactive_subscriptions,
    get_admin_daily_summary,
    get_all_active_subscriptions,
    get_all_short_names,
    get_cached_schedule_snapshot,
    get_session,
    get_subscriptions_due_for_notification,
    get_unique_active_subscription_entities,
    get_user_settings,
    upsert_cached_schedule,
)
from shared_lib.html_tools import split_telegram_html_message
from shared_lib.i18n import translator
from shared_lib.redis_client import redis_client
from shared_lib.request_context import generate_correlation_id, set_correlation_id
from shared_lib.schedule_daily import daily_event_key, deduplicate_daily_recipients
from shared_lib.schedule_outbox import (
    build_schedule_change_event_key,
    claim_schedule_change_deliveries,
    commit_schedule_change_transition,
    enqueue_daily_schedule_delivery,
    get_existing_schedule_deliveries,
    mark_schedule_change_delivery_sent,
    reschedule_schedule_change_delivery,
)
from shared_lib.services.schedule_service import (
    diff_schedules,
    format_schedule,
    get_semester_bounds,
    refresh_cached_schedule_entity_ids_and_semester_cache,
)

# We need to import these from the bot's services.
from shared_lib.services.university_api import RuzAPIClient, RuzAPIError

from .config import (
    BOT_TOKEN,
    SCHEDULE_DAILY_CATCHUP_SECONDS,
    SCHEDULE_OUTBOX_BASE_DELAY_SECONDS,
    SCHEDULE_OUTBOX_MAX_ATTEMPTS,
    TELEGRAM_REQUEST_RETRY_ATTEMPTS,
    TELEGRAM_REQUEST_RETRY_DELAY_SECONDS,
)

logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_LIMIT = 4096


def _filter_schedule_for_subscription(schedule: list[dict], subscription: dict) -> list[dict]:
    """Apply canonical Web/Telegram lesson and module settings before a diff."""
    lesson_mode = subscription.get("lesson_mode", "all")
    selected_modules = set(subscription.get("selected_modules") or [])
    filtered = []
    for lesson in schedule:
        kind = (
            str(lesson.get("kindOfWork") or lesson.get("simple_type") or "")
            .lower()
            .replace("ё", "е")
        )
        if lesson_mode == "exams_only" and not any(
            marker in kind for marker in ("экзам", "зачет", "зачёт", "аттест", "exam", "credit")
        ):
            continue
        module = lesson.get("module")
        if selected_modules and module and module not in selected_modules:
            continue
        filtered.append(lesson)
    return filtered


async def send_telegram_message(
    session: aiohttp.ClientSession,
    chat_id: int,
    text: str,
    message_thread_id: int | None = None,
    reply_markup: dict | None = None,
    request_kwargs: dict | None = None,
    retry_attempts: int | None = None,
    retry_delay_seconds: float | None = None,
) -> dict | None:
    """
    Sends a message using a direct Telegram API call.
    Returns the JSON response result (containing message_id) on success, or None on failure.
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    request_kwargs = request_kwargs or {}
    retries = TELEGRAM_REQUEST_RETRY_ATTEMPTS if retry_attempts is None else max(0, retry_attempts)
    base_delay = (
        TELEGRAM_REQUEST_RETRY_DELAY_SECONDS
        if retry_delay_seconds is None
        else max(0.0, retry_delay_seconds)
    )

    async def post_payload(payload: dict) -> dict | None:
        for attempt in range(retries + 1):
            try:
                async with session.post(url, json=payload, **request_kwargs) as response:
                    if response.status == 200:
                        resp_json = await response.json()
                        logger.info("Sent message to chat %s.", chat_id)
                        return resp_json.get("result")

                    response_text = await response.text()
                    if response.status == 429 and attempt < retries:
                        retry_after = base_delay
                        try:
                            response_json = await response.json()
                            retry_after = max(
                                retry_after,
                                float(response_json.get("parameters", {}).get("retry_after", 0)),
                            )
                        except (TypeError, ValueError, aiohttp.ClientError, json.JSONDecodeError):
                            pass
                        logger.warning(
                            "Telegram rate limited chat %s; retrying in %.2fs (%s/%s).",
                            chat_id,
                            retry_after,
                            attempt + 1,
                            retries,
                        )
                        if retry_after > 0:
                            await asyncio.sleep(retry_after)
                        continue

                    logger.error(
                        "Failed to send message to chat %s. Status: %s, Response: %s",
                        chat_id,
                        response.status,
                        response_text,
                    )
                    return None
            except (TimeoutError, aiohttp.ClientError, OSError) as exc:
                if attempt < retries:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        "Telegram transport error for chat %s; retrying in %.2fs (%s/%s): %s",
                        chat_id,
                        delay,
                        attempt + 1,
                        retries,
                        exc,
                    )
                    if delay > 0:
                        await asyncio.sleep(delay)
                    continue
                logger.error(
                    "Transport error while sending message to chat %s after %s attempt(s): %s",
                    chat_id,
                    retries + 1,
                    exc,
                    exc_info=True,
                )
                return None
        return None

    if len(text) <= TELEGRAM_MESSAGE_LIMIT:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if message_thread_id:
            payload["message_thread_id"] = message_thread_id
        if reply_markup:
            payload["reply_markup"] = reply_markup

        return await post_payload(payload)

    logger.info(
        f"Message for chat {chat_id} is too long ({len(text)} chars). Splitting into HTML-safe chunks."
    )
    chunks = split_telegram_html_message(text, max_chars=3800)
    last_result = None
    for i, chunk in enumerate(chunks):
        payload = {"chat_id": chat_id, "text": chunk, "parse_mode": "HTML"}
        if message_thread_id:
            payload["message_thread_id"] = message_thread_id

        if reply_markup and (i == len(chunks) - 1):
            payload["reply_markup"] = reply_markup

        last_result = await post_payload(payload)
        if last_result is None:
            break

        await asyncio.sleep(0.1)

    logger.info(f"Finished sending all chunks to chat {chat_id}.")
    return last_result


def _format_cached_schedule_timestamp(value: datetime | None, timezone_name: str) -> str:
    if value is None:
        return "unknown"
    normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    try:
        local_value = normalized.astimezone(ZoneInfo(timezone_name))
    except Exception:
        local_value = normalized.astimezone(ZoneInfo("Europe/Moscow"))
    return local_value.strftime("%Y-%m-%d %H:%M %Z")


async def deliver_pending_schedule_change_notifications(
    http_session: aiohttp.ClientSession,
    telegram_request_kwargs: dict | None = None,
) -> dict[str, int]:
    """Deliver one claimed outbox batch and reschedule only failed recipients."""
    summary = {"claimed": 0, "sent": 0, "rescheduled": 0, "failed": 0}
    batch_deadline = time.monotonic() + 45
    # Claim immediately before sending. Reserving 100 rows up front lets later
    # recipients' leases expire while the worker is still sending earlier rows.
    while summary["claimed"] < 100 and time.monotonic() < batch_deadline:
        deliveries = await claim_schedule_change_deliveries(
            limit=1, max_attempts=SCHEDULE_OUTBOX_MAX_ATTEMPTS
        )
        if not deliveries:
            break
        summary["claimed"] += len(deliveries)
        for delivery in deliveries:
            delivery_id = int(delivery["id"])
            attempt_count = int(delivery.get("attempt_count") or 1)
            error_message = "Telegram API did not accept the message"
            try:
                async with asyncio.timeout(840):
                    result = await send_telegram_message(
                        http_session,
                        int(delivery["chat_id"]),
                        str(delivery["payload"]),
                        delivery.get("message_thread_id"),
                        request_kwargs=telegram_request_kwargs,
                    )
                if result is not None:
                    await mark_schedule_change_delivery_sent(
                        delivery_id, expected_attempt_count=attempt_count
                    )
                    summary["sent"] += 1
                    continue
            except Exception as exc:
                error_message = f"{type(exc).__name__}: {exc}"
                logger.error(
                    "Schedule outbox delivery %s failed unexpectedly: %s",
                    delivery_id,
                    exc,
                    exc_info=True,
                )

            terminal = attempt_count >= SCHEDULE_OUTBOX_MAX_ATTEMPTS
            delay_seconds = min(
                SCHEDULE_OUTBOX_BASE_DELAY_SECONDS * (2 ** max(0, attempt_count - 1)),
                6 * 60 * 60,
            )
            await reschedule_schedule_change_delivery(
                delivery_id,
                error=error_message,
                delay_seconds=delay_seconds,
                terminal=terminal,
                expected_attempt_count=attempt_count,
            )
            summary["failed" if terminal else "rescheduled"] += 1

    if summary["claimed"]:
        logger.info("Schedule outbox batch finished: %s", summary)
    return summary


async def send_daily_schedules(
    http_session: aiohttp.ClientSession,
    ruz_api_client: RuzAPIClient,
    telegram_request_kwargs: dict | None = None,
):
    """Durably enqueue due local-date schedules, including a bounded restart catch-up."""
    now = datetime.now(UTC)
    correlation_id = generate_correlation_id(prefix="sched-daily")
    set_correlation_id(correlation_id)
    subscriptions = await get_subscriptions_due_for_notification(
        now, catchup_seconds=SCHEDULE_DAILY_CATCHUP_SECONDS
    )
    subscriptions = deduplicate_daily_recipients(subscriptions)
    keys = [
        (daily_event_key(sub["entity_type"], sub["entity_id"], sub["target_date"]), sub["user_id"])
        for sub in subscriptions
    ]
    existing = await get_existing_schedule_deliveries(keys)
    grouped = collections.defaultdict(list)
    for sub, key in zip(subscriptions, keys, strict=True):
        if key not in existing:
            grouped[(sub["entity_type"], str(sub["entity_id"]), sub["target_date"])].append(sub)
    prepared = 0
    failures = 0
    for (entity_type, entity_id, target_date), recipients in grouped.items():
        using_cache = False
        checked_at = None
        try:
            try:
                schedule_data = await ruz_api_client.get_schedule(
                    entity_type,
                    entity_id,
                    start=target_date.isoformat(),
                    finish=target_date.isoformat(),
                )
                if not isinstance(schedule_data, list):
                    raise ValueError("Unexpected schedule response")
            except Exception:
                schedule_data, checked_at = await get_cached_schedule_snapshot(
                    entity_type, entity_id
                )
                if schedule_data is None:
                    failures += len(recipients)
                    logger.warning("No source for daily schedule %s:%s", entity_type, entity_id)
                    continue
                using_cache = True
            for sub in recipients:
                try:
                    lang = await translator.get_language(sub["user_id"], sub["chat_id"])
                    payload = await format_schedule(
                        schedule_data,
                        lang,
                        sub["entity_name"],
                        entity_type,
                        sub["user_id"],
                        start_date=target_date,
                        is_week_view=False,
                        subscription_id=sub["id"],
                        lesson_mode=sub.get("lesson_mode", "all"),
                    )
                    if using_cache:
                        warning = translator.gettext(
                            lang,
                            "schedule_daily_cache_warning",
                            checked_at=_format_cached_schedule_timestamp(
                                checked_at, sub.get("timezone") or "Europe/Moscow"
                            ),
                        )
                        payload = f"{payload}\n\n{warning}"
                    prepared += await enqueue_daily_schedule_delivery(
                        event_key=daily_event_key(entity_type, entity_id, target_date),
                        subscription=sub,
                        payload=payload,
                    )
                except Exception:
                    failures += 1
                    logger.exception("Failed to prepare daily subscription %s", sub["id"])
        except Exception:
            failures += len(recipients)
            logger.exception("Daily source processing failed for %s:%s", entity_type, entity_id)
    # This also retries messages from earlier ticks when no subscription is newly due.
    delivery = await deliver_pending_schedule_change_notifications(
        http_session, telegram_request_kwargs=telegram_request_kwargs
    )
    summary = {
        "prepared": prepared,
        "failed": failures + delivery["failed"] + delivery["rescheduled"],
        "sent": delivery["sent"],
    }
    logger.info("Daily schedule job finished: %s", summary)
    return summary


async def check_for_schedule_updates(
    http_session: aiohttp.ClientSession,
    ruz_api_client: RuzAPIClient,
    telegram_request_kwargs: dict | None = None,
):
    """
    Periodically check subscriptions and durably enqueue per-user change notifications.

    The outbox is drained both before and after polling. New deliveries are committed before the
    cache/hash checkpoint advances, so a Telegram outage or worker restart cannot silently discard
    an observed change.
    """
    failures = 0
    logger.info("Starting schedule change detection job...")

    start_date_str, end_date_str = get_semester_bounds()

    try:
        try:
            delivery = await deliver_pending_schedule_change_notifications(
                http_session,
                telegram_request_kwargs=telegram_request_kwargs,
            )
            failures += delivery.get("rescheduled", 0) + delivery.get("failed", 0)
        except Exception as exc:
            failures += 1
            logger.error(
                "Failed to drain the schedule-change outbox before polling: %s",
                exc,
                exc_info=True,
            )

        all_subscriptions = await get_all_active_subscriptions()
        if not all_subscriptions:
            return {"failed": failures}

        # Группируем подписки по сущностям (Group/Teacher/Auditorium)
        grouped_subscriptions = collections.defaultdict(list)
        for sub in all_subscriptions:
            if sub.get("delivery_mode", "telegram") != "telegram":
                continue
            entity_key = (sub["entity_type"], sub["entity_id"])
            grouped_subscriptions[entity_key].append(sub)

        for entity_key, entity_subscriptions in list(grouped_subscriptions.items()):
            recipients: dict[int, dict] = {}
            for sub in entity_subscriptions:
                user_id = int(sub["user_id"])
                previous = recipients.get(user_id)
                if previous is None or sub.get("chat_id") == user_id:
                    recipients[user_id] = sub
            grouped_subscriptions[entity_key] = list(recipients.values())

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

                # Treat the entity as the notification unit. If any recipient already carries the
                # new hash, the transition was handled and the remaining rows only need repair.
                reference_hashes = sorted(
                    {
                        str(sub["last_schedule_hash"])
                        for sub in subs_for_entity
                        if sub.get("last_schedule_hash")
                    }
                )
                reference_hash = (
                    new_hash
                    if new_hash in reference_hashes
                    else (reference_hashes[0] if reference_hashes else None)
                )

                if reference_hash and new_hash != reference_hash:
                    logger.info(
                        f"Change detected for entity '{entity_name}' ({entity_type}:{entity_id})."
                    )

                    # 2. Получаем СТАРЫЕ данные из БД (CachedSchedule) для сравнения
                    # Важно сделать это ДО обновления кэша
                    old_schedule_data, source_checked_at = await get_cached_schedule_snapshot(
                        entity_type, entity_id
                    )

                    deliveries = []
                    if old_schedule_data is not None:
                        diffs_by_profile = {}
                        for sub in subs_for_entity:
                            lang = await translator.get_language(sub["user_id"], sub["chat_id"])
                            profile_key = (
                                lang,
                                sub.get("lesson_mode", "all"),
                                tuple(sorted(sub.get("selected_modules") or [])),
                            )
                            if profile_key not in diffs_by_profile:
                                diffs_by_profile[profile_key] = diff_schedules(
                                    _filter_schedule_for_subscription(old_schedule_data, sub),
                                    _filter_schedule_for_subscription(new_schedule_data, sub),
                                    lang,
                                    use_short_names=True,
                                    short_names_map=short_names_map,
                                )

                            diff_text = diffs_by_profile[profile_key]
                            if diff_text:
                                header = translator.gettext(
                                    lang,
                                    "schedule_change_notification",
                                    entity_name=sub["entity_name"],
                                )
                                deliveries.append(
                                    {
                                        "user_id": sub["user_id"],
                                        "chat_id": sub["chat_id"],
                                        "message_thread_id": sub.get("message_thread_id"),
                                        "payload": f"{header}\n\n{diff_text}",
                                    }
                                )

                        event_key = build_schedule_change_event_key(
                            entity_type,
                            entity_id,
                            reference_hash,
                            new_hash,
                            source_checked_at,
                        )
                    else:
                        logger.info(
                            f"Old schedule not found in cache for '{entity_name}'. Skipping diff notification, but updating hash."
                        )
                        event_key = build_schedule_change_event_key(
                            entity_type,
                            entity_id,
                            reference_hash,
                            new_hash,
                            source_checked_at,
                        )

                    # Commit the outbox and checkpoint atomically. If this fails, the next poll
                    # sees the same transition and retries it without losing recipients.
                    await commit_schedule_change_transition(
                        event_key=event_key,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        entity_name=entity_name,
                        schedule_data=new_schedule_data,
                        new_hash=new_hash,
                        deliveries=deliveries,
                    )

                elif not reference_hash:
                    # Если хэша нет (первый запуск для этой подписки), просто сохраняем текущий
                    await batch_update_subscription_hashes(entity_type, entity_id, new_hash)
                    await upsert_cached_schedule(entity_type, entity_id, new_schedule_data)
                else:
                    # The schedule did not change, but the API poll succeeded. Refresh the
                    # DB cache timestamp and repair any divergent per-subscription hashes.
                    await upsert_cached_schedule(entity_type, entity_id, new_schedule_data)
                    await batch_update_subscription_hashes(entity_type, entity_id, new_hash)
                    logger.debug(
                        "Refreshed unchanged schedule cache for %s (%s:%s)",
                        entity_name,
                        entity_type,
                        entity_id,
                    )

                # Небольшая пауза между сущностями, чтобы не грузить API/БД пиками
                await asyncio.sleep(0.5)

            except RuzAPIError as e:
                failures += 1
                logger.warning(f"Change detection: RUZ API error for entity '{entity_name}': {e}")
            except Exception as e:
                failures += 1
                logger.error(
                    f"Change detection: Failed to process entity '{entity_name}': {e}",
                    exc_info=True,
                )

        try:
            delivery = await deliver_pending_schedule_change_notifications(
                http_session,
                telegram_request_kwargs=telegram_request_kwargs,
            )
            failures += delivery.get("rescheduled", 0) + delivery.get("failed", 0)
        except Exception as exc:
            failures += 1
            logger.error(
                "Failed to drain the schedule-change outbox after polling: %s",
                exc,
                exc_info=True,
            )
    except Exception as e:
        failures += 1
        logger.error(f"Critical error in check_for_schedule_updates job: {e}", exc_info=True)

    return {"failed": failures}


async def update_schedule_cache(http_session: aiohttp.ClientSession, ruz_api_client: RuzAPIClient):
    """
    Job to update the cached schedules in the database.
    Fetching the full semester schedule for all active subscriptions.
    """
    failures = 0
    logger.info("Starting schedule cache update job...")

    start_date_str, end_date_str = get_semester_bounds()

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
                failures += 1
                logger.warning(f"Cache update failed for {entity_name}: {e}")
            except Exception as e:
                failures += 1
                logger.error(f"Error caching schedule for {entity_name}: {e}", exc_info=True)

        logger.info("Schedule cache update job finished.")

    except Exception as e:
        failures += 1
        logger.error(f"Critical error in update_schedule_cache job: {e}", exc_info=True)
    return {"failed": failures}


async def refresh_schedule_entity_ids(ruz_api_client: RuzAPIClient):
    """
    Weekly maintenance for semester-specific RUZ ids.

    RUZ numeric ids can change between semesters, so this job searches cached and subscribed
    schedule entities by display name, moves stale references, and refreshes semester cache.
    """
    logger.info("Starting schedule entity id refresh job...")
    try:
        summary = await refresh_cached_schedule_entity_ids_and_semester_cache(ruz_api_client)
        logger.info(
            "Schedule entity id refresh finished. total=%s processed=%s refreshed=%s remapped=%s skipped=%s failed=%s subscriptions_updated=%s web_profiles_updated=%s",
            summary.get("total", 0),
            summary.get("processed", 0),
            summary.get("refreshed", 0),
            summary.get("remapped", 0),
            summary.get("skipped", 0),
            summary.get("failed", 0),
            summary.get("subscriptions_updated", 0) + summary.get("subscriptions_merged", 0),
            summary.get("web_profiles_updated", 0),
        )
    except Exception as e:
        logger.error(f"Critical error in refresh_schedule_entity_ids job: {e}", exc_info=True)


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
                                }
                                await redis_client.set_cache(
                                    redis_key, payload_to_cache, ttl=604800
                                )  # 7 days
                                await redis_client.add_suggestion_message(
                                    data_hash,
                                    chat_id=admin_id,
                                    message_id=msg_result["message_id"],
                                    ttl=604800,
                                )
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

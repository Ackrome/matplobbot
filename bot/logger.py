import logging
import time

from aiogram import BaseMiddleware
from aiogram.types import Update

from shared_lib.request_context import configure_correlation_logging

from .database import log_user_action

logging.getLogger("aiogram.event").setLevel(logging.WARNING)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [cid=%(correlation_id)s] - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler()],
)
configure_correlation_logging()

AVATAR_CACHE_TTL_SECONDS = int(os.getenv("AVATAR_CACHE_TTL_SECONDS", "21600"))
AVATAR_ERROR_CACHE_TTL_SECONDS = int(os.getenv("AVATAR_ERROR_CACHE_TTL_SECONDS", "900"))
_avatar_cache: dict[int, tuple[float, str | None]] = {}


async def _get_avatar_pic_url(bot, user_id: int) -> str | None:
    if not bot or not user_id:
        return None

    now = time.time()
    cached = _avatar_cache.get(user_id)
    if cached and cached[0] > now:
        return cached[1]

    try:
        user_photos = await bot.get_user_profile_photos(user_id, limit=1)
        avatar_pic_url = None
        if user_photos and user_photos.photos and user_photos.photos[0]:
            file_id = user_photos.photos[0][0].file_id
            file_info = await bot.get_file(file_id)
            avatar_pic_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"

        _avatar_cache[user_id] = (now + AVATAR_CACHE_TTL_SECONDS, avatar_pic_url)
        return avatar_pic_url
    except Exception as e:
        logging.warning(f"Failed to fetch avatar for user {user_id}: {e}")
        _avatar_cache[user_id] = (now + AVATAR_ERROR_CACHE_TTL_SECONDS, None)
        return None


class UserLoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Update, data):
        bot = data.get("bot")
        user_id = None
        tg_username = None
        full_name = "Unknown User"
        avatar_pic_url = None
        action_type = "unknown_event"
        action_details = None

        console_log_message = "Received unknown update type."

        if event.message:
            user = event.message.from_user
            user_id = user.id
            tg_username = user.username
            full_name = user.full_name

            if bot and user:
                avatar_pic_url = await _get_avatar_pic_url(bot, user.id)

            if event.message.text and event.message.text.startswith("/"):
                action_type = "command"
                action_details = event.message.text
            elif event.message.text:
                action_type = "text_message"
                action_details = event.message.text
            elif event.message.photo:
                action_type = "photo_message"
                action_details = (
                    f"Photo ID: {event.message.photo[-1].file_id}. "
                    f"Caption: {event.message.caption or ''}"
                )
            elif event.message.document:
                action_type = "document_message"
                action_details = (
                    f"Document: {event.message.document.file_name or 'N/A'}. "
                    f"Caption: {event.message.caption or ''}"
                )
            else:
                action_type = "other_message"
                action_details = f"Message type: {event.message.content_type}"

            console_log_message = (
                f"User: {full_name} (@{tg_username or 'no_username'}), "
                f"Action: {action_type}, Details: {str(action_details)[:100] if action_details else ''}"
            )

        elif event.callback_query:
            user = event.callback_query.from_user
            user_id = user.id
            tg_username = user.username
            full_name = user.full_name

            if bot and user:
                avatar_pic_url = await _get_avatar_pic_url(bot, user.id)

            action_type = "callback_query"
            action_details = event.callback_query.data
            console_log_message = (
                f"User: {full_name} (@{tg_username or 'no_username'}), "
                f"Action: {action_type}, Details: {action_details}"
            )

        logging.info(console_log_message)

        if user_id:
            await log_user_action(
                user_id,
                tg_username,
                full_name,
                avatar_pic_url,
                action_type,
                action_details,
            )

        return await handler(event, data)

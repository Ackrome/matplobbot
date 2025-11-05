from typing import Callable, Dict, Any, Awaitable
import logging

from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, Update

logger = logging.getLogger(__name__)

class GroupMentionCommandMiddleware(BaseMiddleware):
    """
    This middleware processes messages in group chats that start with a mention of the bot.
    If a command follows the mention, it strips the mention so that aiogram's
    command filters can process it as a regular command.
    Example: "@your_bot_name /help" becomes "/help".
    """
    def __init__(self):
        # Cache for the bot's username to avoid repeated API calls.
        self.bot_username = None

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        # We are only interested in message updates
        if not event.message or not isinstance(event.message, Message):
            return await handler(event, data)

        message: Message = event.message
        bot: Bot = data.get('bot')

        # The middleware should only work in group chats and if the message has text and entities.
        if message.chat.type in ("group", "supergroup") and message.text and message.entities and bot:
            # Fetch and cache the bot's username on the first run.
            if self.bot_username is None:
                try:
                    me = await bot.get_me()
                    self.bot_username = me.username
                except Exception as e:
                    logger.error(f"Could not get bot info in GroupMentionCommandMiddleware: {e}")
                    # If we can't get the bot's username, we can't process mentions, so we exit.
                    return await handler(event, data)

            first_entity = message.entities[0]

            # Check if the first entity is a mention at the beginning of the message and it matches the bot's username
            if first_entity.type == "mention" and first_entity.offset == 0:
                mention_text = message.text[first_entity.offset : first_entity.offset + first_entity.length]
                if mention_text == f"@{self.bot_username}":
                    # Modify the message text in-place to remove the mention
                    original_text = message.text
                    message.text = original_text[first_entity.length:].lstrip()

        return await handler(event, data)
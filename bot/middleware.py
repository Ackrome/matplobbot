from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message, Update, Bot


class GroupMentionCommandMiddleware(BaseMiddleware):
    """
    This middleware processes messages in group chats that start with a mention of the bot.
    If a command follows the mention, it strips the mention so that aiogram's
    command filters can process it as a regular command.
    Example: "@your_bot_name /help" becomes "/help".
    """
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
            first_entity = message.entities[0]
            me = await bot.get_me()
            bot_username = me.username

            # Check if the first entity is a mention at the beginning of the message and it matches the bot's username
            if first_entity.type == "mention" and first_entity.offset == 0:
                mention_text = message.text[first_entity.offset : first_entity.offset + first_entity.length]
                if mention_text == f"@{bot_username}":
                    # Modify the message text in-place to remove the mention
                    original_text = message.text
                    message.text = original_text[first_entity.length:].lstrip()

        return await handler(event, data)
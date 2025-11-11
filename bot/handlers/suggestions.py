import logging
from aiogram import F, Router, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
import hashlib
import json

from shared_lib.i18n import translator
from shared_lib.redis_client import redis_client
from shared_lib.database import add_short_name, log_user_action
from ..config import ADMIN_USER_IDS
from ..keyboards import code_path_cache

logger = logging.getLogger(__name__)

class OfferShorterName(StatesGroup):
    awaiting_full_name = State()
    awaiting_short_name = State()

class SuggestionsManager:
    def __init__(self, bot: Bot):
        self.router = Router()
        self.bot = bot
        self._register_handlers()

    def _register_handlers(self):
        self.router.message(Command('offershorter'))(self.cmd_offer_shorter)
        self.router.message(OfferShorterName.awaiting_full_name)(self.process_full_name)
        self.router.message(OfferShorterName.awaiting_short_name)(self.process_short_name)
        self.router.callback_query(F.data.startswith("shorter_name_admin:"))(self.handle_admin_decision)

    async def cmd_offer_shorter(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        lang = await translator.get_language(user_id, message.chat.id)

        # Rate limiting
        limit_key = f"shorter_offer_limit:{user_id}"
        current_count = await redis_client.client.get(limit_key)
        if current_count and int(current_count) >= 5:
            await message.answer(translator.gettext(lang, "shorter_name_limit_exceeded"))
            return

        await state.set_state(OfferShorterName.awaiting_full_name)
        await message.answer(translator.gettext(lang, "shorter_name_prompt_full"))

    async def process_full_name(self, message: Message, state: FSMContext):
        lang = await translator.get_language(message.from_user.id, message.chat.id)
        await state.update_data(full_name=message.text)
        await state.set_state(OfferShorterName.awaiting_short_name)
        await message.answer(translator.gettext(lang, "shorter_name_prompt_short"))

    async def process_short_name(self, message: Message, state: FSMContext):
        user_id = message.from_user.id
        lang = await translator.get_language(user_id, message.chat.id)
        user_data = await state.get_data()
        full_name = user_data['full_name']
        short_name = message.text

        await state.clear()

        # --- NEW: Check for duplicates before adding ---
        pending_offers_raw = await redis_client.client.lrange('pending_shorter_offers', 0, -1)
        is_duplicate = False
        for offer_raw in pending_offers_raw:
            try:
                offer = json.loads(offer_raw)
                if offer.get('full_name') == full_name and offer.get('short_name') == short_name:
                    is_duplicate = True
                    break
            except json.JSONDecodeError:
                continue # Ignore malformed data in Redis

        if is_duplicate:
            await message.answer(translator.gettext(lang, "shorter_name_suggestion_duplicate"))
            return

        # Increment rate limit counter
        limit_key = f"shorter_offer_limit:{user_id}"
        await redis_client.client.incr(limit_key)
        await redis_client.client.expire(limit_key, 86400) # 24 hours

        # --- NEW: Store suggestion in Redis instead of sending immediately ---
        suggestion_payload = json.dumps({'user_id': user_id, 'user_name': message.from_user.full_name, 'full_name': full_name, 'short_name': short_name})
        await redis_client.client.rpush('pending_shorter_offers', suggestion_payload)
        # --- NEW: Log this as a specific user action for statistics ---
        await log_user_action(
            user_id=user_id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
            avatar_pic_url=None, # The middleware will update this on a subsequent action
            action_type='suggestion',
            action_details='offershorter'
        )

        await message.answer(translator.gettext(lang, "shorter_name_suggestion_sent"))

    async def handle_admin_decision(self, callback: CallbackQuery):
        admin_id = callback.from_user.id
        lang = await translator.get_language(admin_id, callback.message.chat.id)

        try:
            _, decision, data_hash = callback.data.split(":")

            # --- REFACTOR: Use Redis instead of in-memory cache ---
            redis_key = f"suggestion_cache:{data_hash}"
            cached_payload = await redis_client.get_cache(redis_key)

            if not cached_payload:
                # This can happen if another admin already actioned it, or if the cache expired.
                await callback.message.edit_text("<i>Это решение уже было принято или данные устарели.</i>")
                await callback.answer()
                return

            # --- NEW: Unpack the more complex payload ---
            original_data = cached_payload['data']
            messages_to_update = cached_payload['messages']
            user_id_str, full_name, short_name = original_data.split(":", 2)
            user_id = int(user_id_str)
            user_lang = await translator.get_language(user_id)

            # --- FIX: Remove the processed suggestion from the Redis list ---
            # Reconstruct the exact payload that was stored in Redis to remove it,
            # using the user_name that is now correctly stored in the cached_payload.
            suggestion_payload_to_remove = json.dumps({'user_id': user_id, 'user_name': cached_payload.get('user_name'), 'full_name': full_name, 'short_name': short_name})
            await redis_client.client.lrem('pending_shorter_offers', 0, suggestion_payload_to_remove)

            if decision == "approve":
                await add_short_name(full_name, short_name, admin_id)
                from shared_lib.services.schedule_service import short_name_cache
                short_name_cache.clear()
                
                final_text = f"{callback.message.text}\n\n**✅ Одобрено администратором {callback.from_user.full_name}.**"
                await self.bot.send_message(
                    user_id,
                    translator.gettext(user_lang, "shorter_name_suggestion_approved", short_name=short_name)
                )
            else: # Decline
                final_text = f"{callback.message.text}\n\n**❌ Отклонено администратором {callback.from_user.full_name}.**"
                await self.bot.send_message(
                    user_id,
                    translator.gettext(user_lang, "shorter_name_suggestion_declined")
                )
            
            # --- NEW: Update the message for ALL admins ---
            for msg_info in messages_to_update:
                # Only edit the message that this specific admin clicked on.
                if msg_info['chat_id'] == callback.message.chat.id and msg_info['message_id'] == callback.message.message_id:
                    try:
                        await self.bot.edit_message_text(final_text, chat_id=msg_info['chat_id'], message_id=msg_info['message_id'], parse_mode='Markdown')
                    except Exception as e:
                        logger.warning(f"Could not edit suggestion message {msg_info['message_id']} for admin {msg_info['chat_id']}: {e}")

            # --- REFACTOR: Remove from Redis cache ---
            await redis_client.client.delete(redis_key)

            await callback.answer()

        except Exception as e:
            logger.error(f"Error handling admin decision for shorter name: {e}", exc_info=True)
            await callback.answer("Произошла ошибка при обработке решения.", show_alert=True)
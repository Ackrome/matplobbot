# bot/handlers/base.py
import logging
from aiogram import F, Router
import inspect
from aiogram.exceptions import TelegramBadRequest
from aiogram import Bot
from aiogram.filters import CommandStart, Command, StateFilter, Filter
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove, InlineKeyboardButton, BotCommand
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .. import keyboards as kb
from .. import database
# Import the manager classes to access their states and methods
from .library import LibraryManager, Search as LibrarySearch
from .github import GitHubManager, MarkdownSearch as GitHubMarkdownSearch
from .schedule import ScheduleManager
from .rendering import RenderingManager, LatexRender, MermaidRender
from .admin import AdminManager, AdminPermissionError
from aiogram import types
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .settings import SettingsManager # Only for type checking

from shared_lib.i18n import translator

class Onboarding(Filter):
    async def __call__(self, message: Message) -> bool:
        return not await database.is_onboarding_completed(message.from_user.id)

class MentionedFilter(Filter):
    """
    Catches messages in groups where the bot is mentioned.
    e.g. "@your_bot_name hello!"
    """
    async def __call__(self, message: Message, bot: Bot) -> bool:
        # The filter should only work in group chats
        if message.chat.type not in ("group", "supergroup"):
            return False

        # Check if the message has entities and any of them is a 'mention'
        if not message.entities:
            return False

        me = await bot.get_me()
        bot_username = me.username

        return any(entity.type == "mention" and message.text[entity.offset:entity.offset + entity.length] == f"@{bot_username}" for entity in message.entities)

class BaseManager:
    def __init__(
        self,
        library_manager: LibraryManager,
        github_manager: GitHubManager,
        schedule_manager: ScheduleManager,
        rendering_manager: RenderingManager,
        admin_manager: AdminManager,
        settings_manager: 'SettingsManager' # Use forward reference for runtime
    ):
        self.router = Router()
        self.library_manager = library_manager
        self.github_manager = github_manager
        self.schedule_manager = schedule_manager
        self.rendering_manager = rendering_manager
        self.admin_manager = admin_manager
        self.settings_manager = settings_manager
        self._register_handlers()

    def _register_handlers(self):
        # Onboarding
        self.router.message(CommandStart(), Onboarding())(self.onboarding_welcome)
        self.router.callback_query(F.data == "onboarding_next", StateFilter("onboarding:welcome"))(self.onboarding_github)
        self.router.callback_query(F.data == "onboarding_next", StateFilter("onboarding:github"))(self.onboarding_library)
        self.router.callback_query(F.data == "onboarding_next", StateFilter("onboarding:library"))(self.onboarding_rendering)
        self.router.callback_query(F.data == "onboarding_next", StateFilter("onboarding:rendering"))(self.onboarding_schedule)
        self.router.callback_query(F.data == "onboarding_next", StateFilter("onboarding:schedule"))(self.onboarding_final)
        self.router.callback_query(F.data == "onboarding_next", StateFilter("onboarding:final"))(self.onboarding_finish)
        self.router.callback_query(F.data == "onboarding_skip", StateFilter("onboarding:welcome"))(self.onboarding_skip)
        # Base Commands
        # Private chat handlers
        self.router.message(CommandStart(), F.chat.type == "private")(self.command_start_regular)
        self.router.message(Command('help'), F.chat.type == "private")(self.command_help_private)
        self.router.message(F.text == "🌐 Language / Язык", F.chat.type == "private")(self.command_cycle_language_reply)

        # Group chat handlers
        self.router.message(CommandStart(), F.chat.type.in_({"group", "supergroup"}))(self.command_start_group)
        self.router.message(Command('help'), F.chat.type.in_({"group", "supergroup"}))(self.command_start_group) # Alias /help to /start in groups

        # Mention handler for groups
        self.router.message(MentionedFilter())(self.handle_mention_in_group)

        # Generic handlers
        self.router.message(StateFilter('*'), Command("cancel"))(self.cancel_handler)
        self.router.message(StateFilter('*'), F.text.casefold() == "отмена")(self.cancel_handler)
        # Help Menu Callbacks
        self.router.callback_query(F.data.startswith("help_cmd_"))(self.cq_help_command_router)
        
        # Error handler for admin permissions
        self.router.error(F.exception.is_(AdminPermissionError))(self.handle_admin_permission_error)


    async def onboarding_welcome(self, event: Message | CallbackQuery, state: FSMContext):
        """Handles the very first step of the onboarding tour."""
        if isinstance(event, CallbackQuery):
            user = event.from_user
            message = event.message
        else: # It's a Message
            user = event.from_user
            message = event
        user_id = user.id

        # --- Automatic Language Detection for New Users ---
        # This logic runs only once when a new user starts the bot.
        settings = await database.get_user_settings(user_id)
        # The default language is 'en'. If the user's client language is different and supported, we switch to it.
        if settings.get('language') == 'en': # Only override the default
            client_lang_code = user.language_code.split('-')[0] if user.language_code else 'en' # e.g., 'ru-RU' -> 'ru'
            if client_lang_code in self.settings_manager.AVAILABLE_LANGUAGES:
                settings['language'] = client_lang_code
                await database.update_user_settings_db(user_id, settings)
                logging.info(f"Automatically set language to '{client_lang_code}' for new user {user_id}.")
        
        # Proceed with onboarding using the detected (or default) language
        lang = await translator.get_language(user_id, message.chat.id)
        await state.set_state("onboarding:welcome") # Ensure state is set for the first step
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_next"), callback_data="onboarding_next"))
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_skip"), callback_data="onboarding_skip"))
        
        # Edit the message if it's a callback, otherwise send a new one.
        if isinstance(event, CallbackQuery):
            await message.edit_text(translator.gettext(lang, "start_onboarding_1"), reply_markup=builder.as_markup())
        else:
            await message.answer(translator.gettext(lang, "start_onboarding_1"), reply_markup=builder.as_markup())

    async def onboarding_github(self, callback: CallbackQuery, state: FSMContext):
        lang = await translator.get_language(callback.from_user.id, callback.message.chat.id)
        await state.set_state("onboarding:github")
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_add_repo"), callback_data="manage_repos"))
        # Add a "Next" button to allow skipping this step
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_next"), callback_data="onboarding_next"))
        await callback.message.edit_text(translator.gettext(lang, "start_onboarding_2"), reply_markup=builder.as_markup())
        await callback.answer()

    async def onboarding_library(self, callback: CallbackQuery, state: FSMContext):
        lang = await translator.get_language(callback.from_user.id, callback.message.chat.id)
        await state.set_state("onboarding:library")
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_browse_library"), callback_data="help_cmd_matp_all"))
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_next"), callback_data="onboarding_next"))
        await callback.message.edit_text(translator.gettext(lang, "start_onboarding_3"), reply_markup=builder.as_markup())
        await callback.answer()

    async def onboarding_rendering(self, callback: CallbackQuery, state: FSMContext):
        lang = await translator.get_language(callback.from_user.id, callback.message.chat.id)
        await state.set_state("onboarding:rendering")
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_try_latex"), callback_data="help_cmd_latex"))
        builder.add(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_next"), callback_data="onboarding_next"))
        await callback.message.edit_text(translator.gettext(lang, "start_onboarding_4"), reply_markup=builder.as_markup())
        await callback.answer()

    async def onboarding_schedule(self, callback: CallbackQuery, state: FSMContext):
        lang = await translator.get_language(callback.from_user.id, callback.message.chat.id)
        await state.set_state("onboarding:schedule")
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_try_schedule"), callback_data="help_cmd_schedule"))
        builder.add(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_next"), callback_data="onboarding_next"))
        await callback.message.edit_text(translator.gettext(lang, "start_onboarding_schedule"), reply_markup=builder.as_markup())
        await callback.answer()

    async def onboarding_final(self, callback: CallbackQuery, state: FSMContext):
        lang = await translator.get_language(callback.from_user.id, callback.message.chat.id)
        await state.set_state("onboarding:final")
        builder = InlineKeyboardBuilder().row(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_finish"), callback_data="onboarding_next"))
        await callback.message.edit_text(translator.gettext(lang, "start_onboarding_5"), reply_markup=builder.as_markup())
        await callback.answer()

    async def onboarding_finish(self, callback: CallbackQuery, state: FSMContext):
        user_id, lang = callback.from_user.id, await translator.get_language(callback.from_user.id, callback.message.chat.id)
        await state.clear()
        await database.set_onboarding_completed(user_id)
        await callback.message.delete() # Clean up the onboarding message
        await callback.message.answer(translator.gettext(lang, "choose_next_command"), reply_markup=await kb.get_main_reply_keyboard(user_id))
        await callback.answer()

    async def onboarding_skip(self, callback: CallbackQuery, state: FSMContext):
        user_id, lang = callback.from_user.id, await translator.get_language(callback.from_user.id, callback.message.chat.id)
        await state.clear()
        await database.set_onboarding_completed(user_id)
        await callback.message.delete() # Clean up the onboarding message
        await callback.message.answer(translator.gettext(lang, "start_welcome", full_name=callback.from_user.full_name), reply_markup=await kb.get_main_reply_keyboard(user_id))
        await callback.answer(translator.gettext(lang, "onboarding_skipped"))
        await callback.answer()

    async def command_start_regular(self, message: Message):
        lang = await translator.get_language(message.from_user.id, message.chat.id)
        await message.answer(translator.gettext(lang, "start_welcome", full_name=message.from_user.full_name), reply_markup=await kb.get_main_reply_keyboard(message.from_user.id))

    async def command_cycle_language_reply(self, message: Message):
        """Handles the language switch from the main reply keyboard."""
        user_id = message.from_user.id
        new_lang = await self.settings_manager._cycle_language(user_id)
        lang_name = self.settings_manager.AVAILABLE_LANGUAGES[new_lang]
        await message.answer(translator.gettext(new_lang, "settings_language_updated", lang_name=lang_name), reply_markup=await kb.get_main_reply_keyboard(user_id))

    async def command_help_private(self, message: Message):
        lang = await translator.get_language(message.from_user.id, message.chat.id)
        await message.answer(translator.gettext(lang, "help_menu_header"), reply_markup=await kb.get_help_inline_keyboard(message.from_user.id))

    async def command_start_group(self, message: Message):
        """Handler for /start or /help in a group chat."""
        lang = await translator.get_language(message.from_user.id, message.chat.id)
        bot_info = await message.bot.get_me()
        bot_username = bot_info.username
        
        # Create a button that links to a private chat with the bot
        keyboard = InlineKeyboardBuilder()
        keyboard.add(InlineKeyboardButton(text=translator.gettext(lang, "group_chat_start_button"), url=f"https://t.me/{bot_username}?start=start"))
        await message.reply(translator.gettext(lang, "group_chat_start_text"), reply_markup=keyboard.as_markup())

    async def handle_mention_in_group(self, message: Message):
        """Handles direct mentions of the bot in a group chat."""
        # Reuse the same logic as /start in a group
        await self.command_start_group(message)

    async def cancel_handler(self, message: Message, state: FSMContext):
        user_id, lang = message.from_user.id, await translator.get_language(message.from_user.id, message.chat.id)
        current_state = await state.get_state()
        if current_state is None:
            await message.answer(translator.gettext(lang, "cancel_no_active_command"), reply_markup=await kb.get_main_reply_keyboard(user_id))
            return
        logging.info(f"Cancelling state {current_state} for user {user_id}")
        await state.clear()
        await message.answer(translator.gettext(lang, "cancel_action_cancelled"), reply_markup=await kb.get_main_reply_keyboard(user_id))

    # --- Help Menu Callbacks ---

    async def cq_help_command_router(self, callback: CallbackQuery, state: FSMContext):
        """A single handler to route all help menu callbacks to their respective command handlers."""
        await callback.answer()
        command_suffix = callback.data.replace("help_cmd_", "")

        # Map command suffixes to their handler methods
        handler_map = {
            "matp_all": self.library_manager.matp_all_command_inline,
            "matp_search": self.library_manager.search_command,
            "schedule": self.schedule_manager.cmd_schedule,
            "myschedule": self.schedule_manager.cmd_my_schedule,
            "lec_search": self.github_manager.lec_search_command,
            "lec_all": self.github_manager.lec_all_command,
            "favorites": self.library_manager.favorites_command,
            "latex": self.rendering_manager.latex_command,
            "mermaid": self.rendering_manager.mermaid_command,
            "settings": self.settings_manager.command_settings_private,
            "help": self.command_help_private,
        }

        handler_func = handler_map.get(command_suffix)

        if not handler_func:
            logging.warning(f"No handler found for help command: {command_suffix}")
            return

        # For certain commands, we need to pass the user object from the callback, not the message
        message = callback.message
        if command_suffix in ["myschedule", "update", "clear_cache"]:
            message.from_user = callback.from_user

        # Inspect the handler to see if it needs the 'state' argument
        handler_signature = inspect.signature(handler_func)
        if 'state' in handler_signature.parameters:
            await handler_func(message, state)
        else:
            await handler_func(message)

    async def handle_admin_permission_error(self, event: types.ErrorEvent):
        """Handles the custom AdminPermissionError gracefully."""
        update = event.update
        user_id = update.callback_query.from_user.id if update.callback_query else update.message.from_user.id
        lang = await translator.get_language(user_id)
        text = translator.gettext(lang, "admin_no_permission")

        if update.message:
            await update.message.reply(text)
        elif update.callback_query:
            await update.callback_query.answer(text, show_alert=True)
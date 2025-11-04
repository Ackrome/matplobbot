# bot/handlers/base.py
import logging
from aiogram import F, Router
import inspect
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove, InlineKeyboardButton
from aiogram.filters import CommandStart, Command, StateFilter, Filter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .. import keyboards as kb
from .. import database
# Import the manager classes to access their states and methods
from .library import LibraryManager, Search as LibrarySearch
from .github import GitHubManager, MarkdownSearch as GitHubMarkdownSearch
from .schedule import ScheduleManager
from .rendering import RenderingManager, LatexRender, MermaidRender
from .admin import AdminManager
from .settings import SettingsManager # Keep this for type hinting
from shared_lib.i18n import translator

class Onboarding(Filter):
    async def __call__(self, message: Message) -> bool:
        return not await database.is_onboarding_completed(message.from_user.id)

class BaseManager:
    def __init__(
        self,
        library_manager: LibraryManager,
        github_manager: GitHubManager,
        schedule_manager: ScheduleManager,
        rendering_manager: RenderingManager,
        admin_manager: AdminManager,
        settings_manager: SettingsManager # This is correct
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
        self.router.message(CommandStart(), Onboarding())(self.command_start_onboarding)
        self.router.callback_query(F.data == "onboarding_next", StateFilter("onboarding:step1"))(self.onboarding_step2)
        self.router.callback_query(F.data == "onboarding_next", StateFilter("onboarding:step2"))(self.onboarding_step3)
        self.router.callback_query(F.data == "onboarding_next", StateFilter("onboarding:step3"))(self.onboarding_step4)
        self.router.callback_query(F.data == "onboarding_next", StateFilter("onboarding:step4"))(self.onboarding_step5)
        self.router.callback_query(F.data == "onboarding_next", StateFilter("onboarding:step5"))(self.onboarding_finish)
        # Base Commands
        self.router.message(CommandStart())(self.command_start_regular)
        self.router.message(Command('help'))(self.command_help)
        self.router.message(StateFilter('*'), Command("cancel"))(self.cancel_handler)
        self.router.message(StateFilter('*'), F.text.casefold() == "отмена")(self.cancel_handler)
        # Help Menu Callbacks
        self.router.callback_query(F.data.startswith("help_cmd_"))(self.cq_help_command_router)

    async def command_start_onboarding(self, message: Message, state: FSMContext):
        user_id, lang = message.from_user.id, await translator.get_user_language(message.from_user.id)
        await state.set_state("onboarding:step1")
        builder = InlineKeyboardBuilder().row(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_next"), callback_data="onboarding_next"))
        await message.answer(translator.gettext(lang, "start_onboarding_1"), reply_markup=builder.as_markup())

    async def onboarding_step2(self, callback: CallbackQuery, state: FSMContext):
        lang = await translator.get_user_language(callback.from_user.id)
        await state.set_state("onboarding:step2")
        builder = InlineKeyboardBuilder().row(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_add_repo"), callback_data="manage_repos"))
        await callback.message.edit_text(translator.gettext(lang, "start_onboarding_2"), reply_markup=builder.as_markup())
        await callback.answer()

    async def onboarding_step3(self, callback: CallbackQuery, state: FSMContext):
        lang = await translator.get_user_language(callback.from_user.id)
        await state.set_state("onboarding:step3")
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_browse_library"), callback_data="help_cmd_matp_all"))
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_next"), callback_data="onboarding_next"))
        await callback.message.edit_text(translator.gettext(lang, "start_onboarding_3"), reply_markup=builder.as_markup())
        await callback.answer()

    async def onboarding_step4(self, callback: CallbackQuery, state: FSMContext):
        lang = await translator.get_user_language(callback.from_user.id)
        await state.set_state("onboarding:step4")
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_try_latex"), callback_data="help_cmd_latex"))
        builder.add(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_next"), callback_data="onboarding_next"))
        await callback.message.edit_text(translator.gettext(lang, "start_onboarding_4"), reply_markup=builder.as_markup())
        await callback.answer()

    async def onboarding_step5(self, callback: CallbackQuery, state: FSMContext):
        lang = await translator.get_user_language(callback.from_user.id)
        await state.set_state("onboarding:step5")
        builder = InlineKeyboardBuilder().row(InlineKeyboardButton(text=translator.gettext(lang, "onboarding_btn_finish"), callback_data="onboarding_next"))
        await callback.message.edit_text(translator.gettext(lang, "start_onboarding_5"), reply_markup=builder.as_markup())
        await callback.answer()

    async def onboarding_finish(self, callback: CallbackQuery, state: FSMContext):
        user_id = callback.from_user.id
        lang = await translator.get_user_language(user_id)
        await state.clear()
        await database.set_onboarding_completed(user_id)
        await callback.message.delete() # Clean up the onboarding message
        await callback.message.answer(translator.gettext(lang, "choose_next_command"), reply_markup=await kb.get_main_reply_keyboard(user_id))
        await callback.answer()

    async def command_start_regular(self, message: Message):
        lang = await translator.get_user_language(message.from_user.id)
        await message.answer(translator.gettext(lang, "start_welcome", full_name=message.from_user.full_name), reply_markup=await kb.get_main_reply_keyboard(message.from_user.id))

    async def command_help(self, message: Message):
        lang = await translator.get_user_language(message.from_user.id)
        await message.answer(translator.gettext(lang, "help_menu_header"), reply_markup=await kb.get_help_inline_keyboard(message.from_user.id))

    async def cancel_handler(self, message: Message, state: FSMContext):
        user_id, lang = message.from_user.id, await translator.get_user_language(message.from_user.id)
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
            "settings": self.settings_manager.command_settings,
            "update": self.admin_manager.update_command,
            "clear_cache": self.admin_manager.clear_cache_command,
            "help": self.command_help,
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
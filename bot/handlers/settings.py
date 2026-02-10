from aiogram import F, Router
from aiogram.filters import Command, and_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from types import SimpleNamespace
import re, datetime
import asyncpg
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .base import BaseManager # Only for type checking
    from .schedule import ScheduleManager
    from .admin import AdminManager
from aiogram import Bot, F
from shared_lib.database import (
    get_user_settings,
    get_user_repos,
    update_user_settings_db,
    get_user_subscriptions,
    remove_schedule_subscription,
    get_chat_subscriptions,
    toggle_subscription_status,
    update_subscription_notification_time,
    get_chat_settings,
    update_chat_settings_db,
    SubscriptionConflictError,
    delete_all_user_data,
    get_all_short_names_with_ids,
    delete_short_name_by_id,
    get_disabled_short_names_for_user,
    toggle_short_name_for_user,
    get_subscription_by_id, 
    update_subscription_modules,
    get_cached_schedule,
    get_subscription_modules
        )
from shared_lib.i18n import translator
from shared_lib.services.schedule_service import get_unique_modules_hybrid
from .admin import AdminOrCreatorFilter
from ..config import ADMIN_USER_IDS
from bot.keyboards import get_modules_keyboard

import logging
logger = logging.getLogger(__name__)

from aiogram import types



AVAILABLE_LANGUAGES = {"en": "English", "ru": "Русский"}
MD_DISPLAY_MODES = ['md_file', 'html_file', 'pdf_file']
SUBSCRIPTIONS_PER_PAGE = 5

class SettingsStates(StatesGroup):
    awaiting_new_sub_time = State()
    awaiting_admin_summary_time = State()

class SettingsManager:
    def __init__(self, schedule_manager: 'ScheduleManager', admin_manager: 'AdminManager'):
        self.router = Router()
        self.schedule_manager = schedule_manager
        self.admin_manager = admin_manager
        self.base_manager: 'BaseManager' | None = None # Will be set later
        self._register_handlers()
        self.AVAILABLE_LANGUAGES = AVAILABLE_LANGUAGES

    def set_base_manager(self, base_manager: 'BaseManager'):
        self.base_manager = base_manager

    def _register_handlers(self):
        # Main settings entry points for private and group chats
        self.router.message(Command('settings'), F.chat.type == "private")(self.command_settings_private)
        self.router.message(Command('settings'), F.chat.type.in_({"group", "supergroup"}), AdminOrCreatorFilter())(self.command_settings_group)

        self.router.callback_query(F.data == "back_to_settings")(self.cq_back_to_settings)

        # Display settings
        self.router.callback_query(F.data == "settings_toggle_short_names")(self.cq_toggle_short_names)
        self.router.callback_query(F.data == "settings_toggle_emojis")(self.cq_toggle_schedule_emojis) 
        self.router.callback_query(F.data == "settings_toggle_emails")(self.cq_toggle_lecturer_emails)
        self.router.callback_query(F.data == "settings_toggle_docstring")(self.cq_toggle_docstring)
        self.router.callback_query(F.data == "settings_cycle_md_mode")(self.cq_cycle_md_mode)

        # Language settings
        self.router.callback_query(F.data == "settings_cycle_language")(self.cq_cycle_language)

        # LaTeX settings
        self.router.callback_query(F.data.startswith("latex_padding_"))(self.cq_change_latex_padding)
        self.router.callback_query(F.data.startswith("latex_dpi_"))(self.cq_change_latex_dpi)

        # Subscription management
        self.router.callback_query(F.data == "manage_personal_subscriptions")(self.cq_subs_list)
        self.router.callback_query(F.data.startswith("subs_page:"))(self.cq_subs_list)
        
        # Открытие карточки
        self.router.callback_query(F.data.startswith("sub_open:"))(self.cq_sub_card)
        
        # Действия внутри карточки
        self.router.callback_query(F.data.startswith("sub_toggle:"))(self.cq_sub_toggle)
        self.router.callback_query(F.data.startswith("sub_del_ask:"))(self.cq_sub_delete_ask)
        self.router.callback_query(F.data.startswith("sub_del_confirm:"))(self.cq_sub_delete_confirm)
        self.router.callback_query(F.data.startswith("sub_time:"))(self.cq_sub_time)
        
        # МОДУЛИ
        self.router.callback_query(F.data.startswith("sub_mods:"))(self.cq_sub_modules_menu)
        
        # Group subscriptions (for admins)
        self.router.callback_query(F.data == "manage_chat_subscriptions")(self.cq_manage_chat_subscriptions)
        self.router.callback_query(F.data.startswith("csub_page:"))(self.cq_manage_chat_subscriptions)
        self.router.callback_query(F.data.startswith("csub_toggle:"))(self.cq_toggle_chat_subscription)
        self.router.callback_query(F.data.startswith("csub_del:"))(self.cq_delete_chat_subscription_prompt)
        self.router.callback_query(F.data.startswith("csub_del_confirm:"))(self.cq_confirm_delete_chat_subscription)
        self.router.callback_query(F.data == "manage_chat_language")(self.cq_cycle_chat_language)
        self.router.callback_query(F.data.startswith("csub_time:"))(self.cq_change_chat_subscription_time_prompt)

        # Handler for when user provides the new time
        self.router.message(SettingsStates.awaiting_new_sub_time)(self.process_new_subscription_time)
        self.router.message(SettingsStates.awaiting_admin_summary_time)(self.process_new_admin_summary_time)

        # Handler for restarting the onboarding tour
        self.router.callback_query(F.data == "restart_onboarding")(self.cq_restart_onboarding_prompt)
        self.router.callback_query(F.data == "restart_onboarding_confirm")(self.cq_confirm_restart_onboarding)

        # Admin-specific settings
        self.router.callback_query(F.data == "admin_settings_summary_time")(self.cq_change_admin_summary_time_prompt)
        self.router.callback_query(F.data == "admin_get_summary_now")(self.cq_get_admin_summary_now)
        self.router.callback_query(F.data.startswith("admin_toggle_summary_day:"))(self.cq_toggle_admin_summary_day)

        # Handlers for deleting all user data
        self.router.callback_query(F.data == "delete_my_data")(self.cq_delete_my_data_prompt)
        self.router.callback_query(F.data == "delete_my_data_confirm")(self.cq_confirm_delete_my_data)

        # --- NEW: Short Name Management Handlers ---
        self.router.callback_query(F.data == "manage_short_names")(self.cq_manage_short_names)
        self.router.callback_query(F.data.startswith("sname_page:"))(self.cq_manage_short_names)
        self.router.callback_query(F.data.startswith("sname_del:"))(self.cq_delete_short_name)
        self.router.callback_query(F.data.startswith("sname_del_confirm:"))(self.cq_confirm_delete_short_name)
        self.router.callback_query(F.data.startswith("sname_toggle:"))(self.cq_toggle_user_short_name)


    async def cq_restart_onboarding_prompt(self, callback: CallbackQuery):
        """Asks the user to confirm restarting the onboarding tour."""
        lang = await translator.get_language(callback.from_user.id, callback.message.chat.id)
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text=translator.gettext(lang, "btn_confirm_restart"), callback_data="restart_onboarding_confirm"),
            InlineKeyboardButton(text=translator.gettext(lang, "btn_cancel"), callback_data="back_to_settings")
        )
        await callback.message.edit_text(
            translator.gettext(lang, "settings_restart_onboarding_confirm"),
            reply_markup=builder.as_markup()
        )
        await callback.answer()

    async def cq_confirm_restart_onboarding(self, callback: CallbackQuery, state: FSMContext):
        """Handles the actual restart of the onboarding process."""
        await state.clear() # Clear any previous state
        await self.base_manager.onboarding_welcome(callback, state)

    async def cq_delete_my_data_prompt(self, callback: CallbackQuery):
        """Asks the user for final confirmation before deleting all their data."""
        lang = await translator.get_language(callback.from_user.id, callback.message.chat.id)
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text=translator.gettext(lang, "btn_confirm_delete_all_data"), callback_data="delete_my_data_confirm"),
            InlineKeyboardButton(text=translator.gettext(lang, "btn_cancel"), callback_data="back_to_settings")
        )
        await callback.message.edit_text(translator.gettext(lang, "settings_delete_my_data_confirm"), reply_markup=builder.as_markup())
        await callback.answer()

    async def cq_confirm_delete_my_data(self, callback: CallbackQuery):
        """Handles the actual deletion of all user data."""
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id, callback.message.chat.id)
        success = await delete_all_user_data(user_id)
        if success:
            await callback.message.edit_text(translator.gettext(lang, "delete_my_data_success"))
        else:
            await callback.message.edit_text(translator.gettext(lang, "delete_my_data_error"))
        await callback.answer()

    # --- NEW: Modular Keyboard Building Functions ---

    async def _build_display_settings(self, builder: InlineKeyboardBuilder, settings: dict, lang: str):
        """Builds buttons related to how information is displayed."""
        # Short Names Toggle
        short_names_status_key = "settings_docstring_on" if settings.get('use_short_names', True) else "settings_docstring_off"
        builder.row(InlineKeyboardButton(
            text=translator.gettext(lang, "settings_use_short_names", status=translator.gettext(lang, short_names_status_key)),
            callback_data="settings_toggle_short_names"
        ))
        emojis_status_key = "settings_docstring_on" if settings.get('show_schedule_emojis', True) else "settings_docstring_off"
        builder.row(InlineKeyboardButton(
            text=translator.gettext(lang, "settings_show_schedule_emojis", status=translator.gettext(lang, emojis_status_key)),
            callback_data="settings_toggle_emojis"
        ))
        emails_status_key = "settings_docstring_on" if settings.get('show_lecturer_emails', True) else "settings_docstring_off"
        builder.row(InlineKeyboardButton(
            text=translator.gettext(lang, "settings_show_lecturer_emails", status=translator.gettext(lang, emails_status_key)),
            callback_data="settings_toggle_emails"
        ))
        # Docstring toggle
        docstring_status_key = "settings_docstring_on" if settings['show_docstring'] else "settings_docstring_off"
        builder.row(InlineKeyboardButton(
            text=translator.gettext(lang, "settings_show_docstring", status=translator.gettext(lang, docstring_status_key)),
            callback_data="settings_toggle_docstring"
        ))
        # Markdown display mode
        md_mode = settings.get('md_display_mode', 'md_file')
        md_mode_map = {
            'md_file': translator.gettext(lang, 'settings_md_mode_md'),
            'html_file': translator.gettext(lang, 'settings_md_mode_html'),
            'pdf_file': translator.gettext(lang, 'settings_md_mode_pdf')
        }
        md_mode_text = md_mode_map.get(md_mode, translator.gettext(lang, 'settings_md_mode_unknown'))
        builder.row(InlineKeyboardButton(
            text=translator.gettext(lang, "settings_md_display_mode", mode_text=md_mode_text),
            callback_data="settings_cycle_md_mode"
        ))

    async def _build_latex_settings(self, builder: InlineKeyboardBuilder, settings: dict, lang: str):
        """Builds buttons for LaTeX rendering options."""
        builder.row(
            InlineKeyboardButton(text="➖", callback_data="latex_padding_decr"),
            InlineKeyboardButton(text=translator.gettext(lang, "settings_latex_padding", padding=settings['latex_padding']), callback_data="noop"),
            InlineKeyboardButton(text="➕", callback_data="latex_padding_incr")
        )
        builder.row(
            InlineKeyboardButton(text="➖", callback_data="latex_dpi_decr"),
            InlineKeyboardButton(text=translator.gettext(lang, "settings_latex_dpi", dpi=settings['latex_dpi']), callback_data="noop"),
            InlineKeyboardButton(text="➕", callback_data="latex_dpi_incr")
        )

    async def _build_data_management_settings(self, builder: InlineKeyboardBuilder, user_id: int, lang: str):
        """Builds buttons for managing user-specific data."""
        user_repos = await get_user_repos(user_id)
        repo_button_key = "settings_manage_repos_btn" if user_repos else "settings_add_repos_btn"
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, repo_button_key), callback_data="manage_repos"))
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "settings_manage_subscriptions_btn"), callback_data="manage_personal_subscriptions"))
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "settings_manage_short_names_btn"), callback_data="manage_short_names"))
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "settings_delete_my_data_btn"), callback_data="delete_my_data"))

    async def _build_admin_settings(self, builder: InlineKeyboardBuilder, settings: dict, lang: str):
        """Builds admin-only settings buttons."""
        summary_time = settings.get('admin_daily_summary_time', '09:00')
        builder.row(InlineKeyboardButton(
            text=translator.gettext(lang, "admin_settings_summary_time_btn", time=summary_time),
            callback_data="admin_settings_summary_time"
        ))
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "admin_get_summary_now_btn"), callback_data="admin_get_summary_now"))
        summary_days = settings.get('admin_summary_days', [0, 1, 2, 3, 4])
        day_names = translator.gettext(lang, "calendar_days_short").split(',')
        day_buttons = [InlineKeyboardButton(text=f"{'✅' if i in summary_days else '❌'} {day_name}", callback_data=f"admin_toggle_summary_day:{i}") for i, day_name in enumerate(day_names)]
        builder.row(*day_buttons)

    async def get_settings_keyboard(self, user_id: int) -> InlineKeyboardBuilder:
        """Creates the main inline keyboard for user settings."""
        settings = await get_user_settings(user_id)
        lang = settings.get('language', 'en')
        builder = InlineKeyboardBuilder()

        await self._build_display_settings(builder, settings, lang)
        await self._build_latex_settings(builder, settings, lang)
        await self._build_data_management_settings(builder, user_id, lang)

        current_lang_name = AVAILABLE_LANGUAGES.get(lang, "Unknown")
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "settings_language_btn", lang_name=current_lang_name), callback_data="settings_cycle_language"))
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "settings_restart_onboarding_btn"), callback_data="restart_onboarding"))

        if user_id in ADMIN_USER_IDS:
            await self._build_admin_settings(builder, settings, lang)

        return builder

    async def _get_group_settings_menu(self, chat_id: int, user_id: int) -> tuple[str, InlineKeyboardBuilder]:
        """Helper to build the text and keyboard for the group settings menu."""
        lang = await translator.get_language(user_id, chat_id)
        chat_settings = await get_chat_settings(chat_id)
        current_lang_name = AVAILABLE_LANGUAGES.get(chat_settings.get('language', 'en'), "Unknown")

        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "settings_manage_chat_subscriptions_btn"), callback_data="manage_chat_subscriptions"))
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "settings_language_btn", lang_name=current_lang_name), callback_data="manage_chat_language"))
        
        text = translator.gettext(lang, "settings_group_menu_header")
        return text, builder

    async def command_settings_private(self, message: Message):
        user_id = message.from_user.id
        lang = await translator.get_language(user_id)
        keyboard = await self.get_settings_keyboard(user_id)
        await message.answer(translator.gettext(lang, "settings_menu_header"), reply_markup=keyboard.as_markup())

    async def command_settings_group(self, message: Message):
        """Handler for /settings in a group, for admins."""
        text, builder = await self._get_group_settings_menu(message.chat.id, message.from_user.id)
        await message.reply(text, reply_markup=builder.as_markup())


    async def cq_back_to_settings(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id)
        keyboard = await self.get_settings_keyboard(user_id)
        await callback.message.edit_text(translator.gettext(lang, "settings_menu_header"), reply_markup=keyboard.as_markup())
        await callback.answer()

    async def cq_toggle_schedule_emojis(self, callback: CallbackQuery):
        """Toggles the display of colored squares in the schedule."""
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id)
        settings = await get_user_settings(user_id)
        
        # Toggle the boolean
        settings['show_schedule_emojis'] = not settings.get('show_schedule_emojis', True)
        
        await update_user_settings_db(user_id, settings)
        
        keyboard = await self.get_settings_keyboard(user_id)
        await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
        await callback.answer(translator.gettext(lang, "settings_schedule_emojis_updated"))
    
    async def cq_toggle_lecturer_emails(self, callback: CallbackQuery):
        """Toggles the display of lecturer emails in the schedule."""
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id)
        settings = await get_user_settings(user_id)
        
        # Toggle the boolean
        settings['show_lecturer_emails'] = not settings.get('show_lecturer_emails', True)
        
        await update_user_settings_db(user_id, settings)
        
        keyboard = await self.get_settings_keyboard(user_id)
        await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
        await callback.answer(translator.gettext(lang, "settings_lecturer_emails_updated"))

    async def cq_toggle_short_names(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id)
        settings = await get_user_settings(user_id)
        settings['use_short_names'] = not settings.get('use_short_names', True)
        await update_user_settings_db(user_id, settings)
        keyboard = await self.get_settings_keyboard(user_id)
        await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
        await callback.answer(translator.gettext(lang, "settings_short_names_updated"))


    async def cq_toggle_docstring(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id)
        settings = await get_user_settings(user_id)
        settings['show_docstring'] = not settings['show_docstring']
        await update_user_settings_db(user_id, settings)
        keyboard = await self.get_settings_keyboard(user_id)
        await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
        await callback.answer(translator.gettext(lang, "settings_docstring_updated"))

    async def cq_cycle_md_mode(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id)
        settings = await get_user_settings(user_id)
        current_mode = settings.get('md_display_mode', 'md_file')
        try:
            current_index = MD_DISPLAY_MODES.index(current_mode)
            new_mode = MD_DISPLAY_MODES[(current_index + 1) % len(MD_DISPLAY_MODES)]
        except ValueError:
            new_mode = MD_DISPLAY_MODES[0]
        settings['md_display_mode'] = new_mode
        await update_user_settings_db(user_id, settings)
        keyboard = await self.get_settings_keyboard(user_id)
        await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
        await callback.answer(translator.gettext(lang, "settings_md_mode_updated", mode_text=new_mode))

    async def _cycle_language(self, user_id: int) -> str:
        """
        Cycles the language for a user, saves it, and returns the new language code.
        This helper function can be called from different handlers.
        """
        settings = await get_user_settings(user_id)
        current_lang = settings.get('language', 'en')
        language_codes = list(AVAILABLE_LANGUAGES.keys())
        try:
            current_index = language_codes.index(current_lang)
            new_lang = language_codes[(current_index + 1) % len(language_codes)]
        except ValueError:
            new_lang = language_codes[0] # Default to the first language if something is wrong
        settings['language'] = new_lang
        await update_user_settings_db(user_id, settings)
        return new_lang

    async def cq_cycle_language(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        settings = await get_user_settings(user_id)
        current_lang = settings.get('language', 'en')
        language_codes = list(AVAILABLE_LANGUAGES.keys())
        try:
            current_index = language_codes.index(current_lang)
            new_lang = language_codes[(current_index + 1) % len(language_codes)]
        except ValueError:
            new_lang = language_codes[0]
        settings['language'] = new_lang
        new_lang = await self._cycle_language(user_id)
        keyboard = await self.get_settings_keyboard(user_id)
        await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
        await callback.answer(translator.gettext(new_lang, "settings_language_updated", lang_name=AVAILABLE_LANGUAGES[new_lang]))

    async def cq_cycle_chat_language(self, callback: CallbackQuery):
        """Cycles the language for the entire group chat."""
        chat_id = callback.message.chat.id
        
        chat_settings = await get_chat_settings(chat_id)
        current_lang = chat_settings.get('language', 'en')
        language_codes = list(AVAILABLE_LANGUAGES.keys())
        try:
            current_index = language_codes.index(current_lang)
            new_lang = language_codes[(current_index + 1) % len(language_codes)]
        except ValueError:
            new_lang = language_codes[0]
        chat_settings['language'] = new_lang
        await update_chat_settings_db(chat_id, chat_settings)
        
        # Edit the existing message instead of sending a new one
        text, builder = await self._get_group_settings_menu(chat_id, callback.from_user.id)
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer(translator.gettext(new_lang, "settings_language_updated", lang_name=AVAILABLE_LANGUAGES[new_lang]))

    async def cq_change_latex_padding(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id)
        settings = await get_user_settings(user_id)
        current_padding = settings.get('latex_padding', 15)
        action = callback.data.split('_')[-1]
        new_padding = max(0, current_padding + 5) if action == "incr" else max(0, current_padding - 5)
        if new_padding != current_padding:
            settings['latex_padding'] = new_padding
            await update_user_settings_db(user_id, settings)
            keyboard = await self.get_settings_keyboard(user_id)
            await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
        await callback.answer(translator.gettext(lang, "settings_latex_padding_changed", padding=new_padding))

    async def cq_change_latex_dpi(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id)
        settings = await get_user_settings(user_id)
        current_dpi = settings.get('latex_dpi', 300)
        action = callback.data.split('_')[-1]
        new_dpi = min(600, current_dpi + 50) if action == "incr" else max(100, current_dpi - 50)
        if new_dpi != current_dpi:
            settings['latex_dpi'] = new_dpi
            await update_user_settings_db(user_id, settings)
            keyboard = await self.get_settings_keyboard(user_id)
            await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
        await callback.answer(translator.gettext(lang, "settings_latex_dpi_changed", dpi=new_dpi))

    async def get_personal_subscriptions_keyboard(self, user_id: int, page: int = 0) -> InlineKeyboardBuilder:
        lang = await translator.get_language(user_id)
        subscriptions, total_count = await get_user_subscriptions(user_id, page=page, page_size=SUBSCRIPTIONS_PER_PAGE)
        builder = InlineKeyboardBuilder()
        for sub in subscriptions:
            # Determine if the subscription is for a private chat or a group
            # A subscription is private if the creator's ID is the same as the target chat ID
            status_emoji = "✅" if sub['is_active'] else "❌"
            is_private = sub['user_id'] == sub['chat_id']
            target_label = "👤 Private" if is_private else "👥 Group"
            
            # Create a more descriptive button text
            button_text = f"{status_emoji} {sub['entity_name']}"
            
            toggle_button_text = translator.gettext(lang, "btn_disable") if sub['is_active'] else translator.gettext(lang, "btn_enable")
            builder.row(
                InlineKeyboardButton(text=button_text, callback_data="noop"),
                InlineKeyboardButton(text=toggle_button_text, callback_data=f"psub_toggle:{sub['id']}:{page}"),
                InlineKeyboardButton(text=f"⏰ {sub['notification_time']}", callback_data=f"psub_time:{sub['id']}:{page}"),
                InlineKeyboardButton(text=translator.gettext(lang, "btn_delete"), callback_data=f"psub_del:{sub['id']}:{page}"),
                InlineKeyboardButton(text=target_label, callback_data="noop"),

            )
        total_pages = (total_count + SUBSCRIPTIONS_PER_PAGE - 1) // SUBSCRIPTIONS_PER_PAGE
        if total_pages > 1:
            pagination_buttons = []
            if page > 0: pagination_buttons.append(InlineKeyboardButton(text=translator.gettext(lang, "pagination_back"), callback_data=f"psub_page:{page - 1}"))
            pagination_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
            if (page + 1) < total_pages: pagination_buttons.append(InlineKeyboardButton(text=translator.gettext(lang, "pagination_forward"), callback_data=f"psub_page:{page + 1}"))
            builder.row(*pagination_buttons)
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "back_to_settings"), callback_data="back_to_settings"))
        return builder

    async def get_chat_subscriptions_keyboard(self, chat_id: int, lang: str, page: int = 0) -> InlineKeyboardBuilder:
        """Builds the keyboard for managing subscriptions within a specific chat."""
        subscriptions, total_count = await get_chat_subscriptions(chat_id, page=page, page_size=SUBSCRIPTIONS_PER_PAGE)
        builder = InlineKeyboardBuilder()
        for sub in subscriptions:
            status_emoji = "✅" if sub['is_active'] else "❌"
            button_text = f"{status_emoji} {sub['entity_name']} ({sub['notification_time']})"
            toggle_button_text = translator.gettext(lang, "btn_disable") if sub['is_active'] else translator.gettext(lang, "btn_enable")
            builder.row(
                InlineKeyboardButton(text=button_text, callback_data="noop"),
                InlineKeyboardButton(text=toggle_button_text, callback_data=f"csub_toggle:{sub['id']}:{page}"),
                InlineKeyboardButton(text=f"⏰ {sub['notification_time']}", callback_data=f"csub_time:{sub['id']}:{page}"),
                InlineKeyboardButton(text=translator.gettext(lang, "btn_delete"), callback_data=f"csub_del:{sub['id']}:{page}")
            )
        total_pages = (total_count + SUBSCRIPTIONS_PER_PAGE - 1) // SUBSCRIPTIONS_PER_PAGE
        if total_pages > 1:
            pagination_buttons = []
            if page > 0: pagination_buttons.append(InlineKeyboardButton(text=translator.gettext(lang, "pagination_back"), callback_data=f"csub_page:{page - 1}"))
            pagination_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
            if (page + 1) < total_pages: pagination_buttons.append(InlineKeyboardButton(text=translator.gettext(lang, "pagination_forward"), callback_data=f"csub_page:{page + 1}"))
            builder.row(*pagination_buttons)
        # No "back to settings" button needed here as it's a transient menu in a group.
        return builder

    async def cq_manage_personal_subscriptions(self, callback: CallbackQuery, state: FSMContext):
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id)
        page = int(callback.data.split(":")[1]) if callback.data.startswith("psub_page:") else 0
        _, total_count = await get_user_subscriptions(user_id, page=page, page_size=SUBSCRIPTIONS_PER_PAGE)
        header_text = translator.gettext(lang, "subscriptions_header") if total_count > 0 else translator.gettext(lang, "subscriptions_empty")
        keyboard = await self.get_personal_subscriptions_keyboard(user_id, page=page)
        await callback.message.edit_text(header_text, reply_markup=keyboard.as_markup())
        await callback.answer()

    async def cq_manage_chat_subscriptions(self, callback: CallbackQuery, state: FSMContext):
        user_id = callback.from_user.id
        chat_id = callback.message.chat.id
        lang = await translator.get_language(user_id, chat_id)
        page = int(callback.data.split(":")[1]) if callback.data.startswith("csub_page:") else 0
        _, total_count = await get_chat_subscriptions(chat_id, page=page, page_size=SUBSCRIPTIONS_PER_PAGE)
        header_text = translator.gettext(lang, "subscriptions_chat_header") if total_count > 0 else translator.gettext(lang, "subscriptions_empty")
        keyboard = await self.get_chat_subscriptions_keyboard(chat_id, lang, page=page)
        await callback.message.edit_text(header_text, reply_markup=keyboard.as_markup())
        await callback.answer()

    async def cq_toggle_personal_subscription(self, callback: CallbackQuery, state: FSMContext): # Keep this handler
        user_id, lang = callback.from_user.id, await translator.get_language(callback.from_user.id)
        try:
            _, subscription_id_str, page_str = callback.data.split(":")
            toggle_result = await toggle_subscription_status(int(subscription_id_str), user_id, is_chat_admin=False)
            if toggle_result:
                new_status, entity_name = toggle_result
                status_text = "enabled" if new_status else "disabled"
                await callback.answer(translator.gettext(lang, f"subscription_{status_text}", entity_name=entity_name))
                # Refresh the keyboard
                callback.data = f"psub_page:{page_str}"
                await self.cq_manage_personal_subscriptions(callback, state)
            else:
                await callback.answer(translator.gettext(lang, "subscription_info_outdated"), show_alert=True)
        except (ValueError, IndexError):
            await callback.answer(translator.gettext(lang, "subscription_info_outdated"), show_alert=True)

    async def cq_toggle_chat_subscription(self, callback: CallbackQuery, state: FSMContext): # Keep this handler
        user_id, lang = callback.from_user.id, await translator.get_language(callback.from_user.id, callback.message.chat.id)
        try:
            _, subscription_id_str, page_str = callback.data.split(":")
            toggle_result = await toggle_subscription_status(int(subscription_id_str), user_id, is_chat_admin=True)
            if toggle_result:
                new_status, entity_name = toggle_result
                status_text = "enabled" if new_status else "disabled"
                await callback.answer(translator.gettext(lang, f"subscription_{status_text}", entity_name=entity_name))
                # Refresh the keyboard
                callback.data = f"csub_page:{page_str}"
                await self.cq_manage_chat_subscriptions(callback, state)
            else:
                await callback.answer(translator.gettext(lang, "subscription_info_outdated"), show_alert=True)
        except (ValueError, IndexError):
            await callback.answer(translator.gettext(lang, "subscription_info_outdated"), show_alert=True)

    # --- NEW TIME CHANGE HANDLERS ---

    async def cq_change_personal_subscription_time_prompt(self, callback: CallbackQuery, state: FSMContext):
        user_id, lang = callback.from_user.id, await translator.get_language(callback.from_user.id)
        try:
            _, subscription_id_str, page_str = callback.data.split(":")
            await state.set_state(SettingsStates.awaiting_new_sub_time) # Set state first
            await state.update_data(sub_id=int(subscription_id_str), page=int(page_str), is_chat_admin=False, original_chat_id=callback.message.chat.id, original_message_id=callback.message.message_id)
            await callback.message.edit_text(translator.gettext(lang, "subscription_change_time_prompt"))
            await callback.answer()
        except (ValueError, IndexError):
            await callback.answer(translator.gettext(lang, "subscription_info_outdated"), show_alert=True)

    async def cq_change_chat_subscription_time_prompt(self, callback: CallbackQuery, state: FSMContext):
        user_id, lang = callback.from_user.id, await translator.get_language(callback.from_user.id, callback.message.chat.id)
        try:
            _, subscription_id_str, page_str = callback.data.split(":")
            await state.set_state(SettingsStates.awaiting_new_sub_time)
            await state.update_data(sub_id=int(subscription_id_str), page=int(page_str), is_chat_admin=True)
            await callback.message.edit_text(translator.gettext(lang, "subscription_change_time_prompt"))
            await callback.answer()
        except (ValueError, IndexError):
            await callback.answer(translator.gettext(lang, "subscription_info_outdated"), show_alert=True)

    async def cq_change_admin_summary_time_prompt(self, callback: CallbackQuery, state: FSMContext):
        lang = await translator.get_language(callback.from_user.id)
        await state.set_state(SettingsStates.awaiting_admin_summary_time)
        await callback.message.edit_text(translator.gettext(lang, "admin_settings_summary_time_prompt"))
        await callback.answer()

    async def cq_get_admin_summary_now(self, callback: CallbackQuery, bot: Bot):
        """Handles the 'Get Summary Now' button click for admins."""
        await callback.answer("Запрашиваю сводку...")
        # We reuse the command handler, passing the admin's ID as the target.
        # The key fix is to pass the admin's ID (from `callback.from_user.id`)
        # as the `target_chat_id` to the command handler.
        await self.admin_manager.send_admin_summary_command(callback.message, bot, target_chat_id=callback.from_user.id)

    async def cq_toggle_admin_summary_day(self, callback: CallbackQuery):
        """Toggles a day for the admin's daily summary."""
        user_id = callback.from_user.id
        try:
            day_to_toggle = int(callback.data.split(":")[1])
            settings = await get_user_settings(user_id)
            summary_days = settings.get('admin_summary_days', [])
            if day_to_toggle in summary_days:
                summary_days.remove(day_to_toggle)
            else:
                summary_days.append(day_to_toggle)
            settings['admin_summary_days'] = sorted(summary_days)
            await update_user_settings_db(user_id, settings)
            keyboard = await self.get_settings_keyboard(user_id)
            await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
        except (ValueError, IndexError):
            logger.error(f"Invalid admin_toggle_summary_day callback data: {callback.data}")
        finally:
            await callback.answer()

    async def process_new_subscription_time(self, message: Message, state: FSMContext, bot: Bot):
        user_id, lang = message.from_user.id, await translator.get_language(message.from_user.id, message.chat.id)
        time_str = message.text.strip()

        if not re.match(r"^\d{1,2}:\d{2}$", time_str):
            await message.reply(translator.gettext(lang, "schedule_invalid_time_format"))
            return
        
        try:
            new_time = datetime.datetime.strptime(time_str, "%H:%M").time()
            state_data = await state.get_data()
            sub_id, page, is_chat_admin = state_data['sub_id'], state_data['page'], state_data['is_chat_admin']
            original_chat_id = state_data['original_chat_id']
            original_message_id = state_data['original_message_id']
            
            updated_entity_name = await update_subscription_notification_time(sub_id, new_time, user_id, is_chat_admin)
            
            if updated_entity_name:
                await message.answer(translator.gettext(lang, "subscription_time_updated", entity_name=updated_entity_name, time_str=time_str))
                
                # Delete the user's message to keep the chat clean
                try:
                    await message.delete()
                except TelegramBadRequest as e:
                    logger.warning(f"Could not delete user's time message: {e}")

                # Create a mock object that mimics a CallbackQuery to refresh the menu.
                # This is necessary because the target handlers expect a CallbackQuery object, not a Message.
                mock_callback = SimpleNamespace(
                    message=types.Message(chat=types.Chat(id=original_chat_id, type='private'), message_id=original_message_id, date=datetime.datetime.now()),
                    from_user=message.from_user,
                    bot=bot,
                    # Вместо psub_page используем sub_open
                    data=f"sub_open:{sub_id}"
                )
                
                if is_chat_admin:
                    # Для групповых чатов пока можно оставить старую логику или адаптировать позже
                    await self.cq_manage_chat_subscriptions(mock_callback, state)
                else:
                    # Для личных подписок идем в карточку
                    await self.cq_sub_card(mock_callback) 
            else:
                await message.answer(translator.gettext(lang, "subscription_update_failed_general")) # Use answer instead of reply
        except SubscriptionConflictError:
            await message.answer(translator.gettext(lang, "subscription_time_conflict_error")) # Use answer instead of reply
        except ValueError:
            await message.answer(translator.gettext(lang, "schedule_invalid_time_value")) # Use answer instead of reply
        except Exception as e: # Catch any other unexpected errors during DB operation
            logging.error(f"Unexpected error updating subscription time for sub {sub_id}: {e}", exc_info=True)
            await message.answer(translator.gettext(lang, "subscription_update_failed_general")) # Use answer instead of reply
        finally:
            await state.clear()

    async def process_new_admin_summary_time(self, message: Message, state: FSMContext):
        """Handles the new time input for the admin's daily summary."""
        user_id, lang = message.from_user.id, await translator.get_language(message.from_user.id, message.chat.id)
        time_str = message.text.strip()

        if not re.match(r"^\d{1,2}:\d{2}$", time_str):
            await message.reply(translator.gettext(lang, "schedule_invalid_time_format"))
            return

        try:
            new_time = datetime.datetime.strptime(time_str, "%H:%M").time()
            settings = await get_user_settings(user_id)
            settings['admin_daily_summary_time'] = new_time.strftime("%H:%M")
            await update_user_settings_db(user_id, settings)
            await message.answer(translator.gettext(lang, "admin_summary_time_updated", time=new_time.strftime("%H:%M")))
        except ValueError:
            await message.answer(translator.gettext(lang, "schedule_invalid_time_value"))
        finally:
            await state.clear()
            # Show the main settings menu again
            keyboard = await self.get_settings_keyboard(user_id)
            await message.answer(translator.gettext(lang, "settings_menu_header"), reply_markup=keyboard.as_markup())

    # --- NEW DELETION HANDLERS ---

    async def cq_delete_personal_subscription_prompt(self, callback: CallbackQuery):
        user_id, lang = callback.from_user.id, await translator.get_language(callback.from_user.id)
        try:
            _, subscription_id_str, page_str = callback.data.split(":")
            subscription_id = int(subscription_id_str)
            subscriptions, _ = await get_user_subscriptions(user_id, page=0, page_size=1000) # Fetch all to find the one
            sub_to_delete = next((sub for sub in subscriptions if sub['id'] == subscription_id), None)
            if not sub_to_delete: raise ValueError("Subscription not found")
            
            builder = InlineKeyboardBuilder().row(
                InlineKeyboardButton(text=translator.gettext(lang, "btn_confirm_delete"), callback_data=f"psub_del_confirm:{subscription_id}:{page_str}"),
                InlineKeyboardButton(text=translator.gettext(lang, "btn_cancel"), callback_data=f"psub_page:{page_str}")
            )
            await callback.message.edit_text(translator.gettext(lang, "subscription_confirm_delete", entity_name=sub_to_delete['entity_name']), reply_markup=builder.as_markup())
            await callback.answer()
        except (ValueError, IndexError):
            await callback.answer(translator.gettext(lang, "subscription_info_outdated"), show_alert=True)

    async def cq_confirm_delete_personal_subscription(self, callback: CallbackQuery, state: FSMContext):
        user_id, lang = callback.from_user.id, await translator.get_language(callback.from_user.id)
        try:
            _, subscription_id_str, page_str = callback.data.split(":")
            deleted_entity_name = await remove_schedule_subscription(int(subscription_id_str), user_id, is_chat_admin=False)
            if deleted_entity_name:
                await callback.answer(translator.gettext(lang, "subscription_removed", entity_name=deleted_entity_name))
                callback.data = f"psub_page:{page_str}"
                await self.cq_manage_personal_subscriptions(callback, state)
            else:
                await callback.answer(translator.gettext(lang, "subscription_info_outdated"), show_alert=True)
        except (ValueError, IndexError):
            await callback.answer(translator.gettext(lang, "subscription_info_outdated"), show_alert=True)

    async def cq_delete_chat_subscription_prompt(self, callback: CallbackQuery):
        user_id, lang = callback.from_user.id, await translator.get_language(callback.from_user.id, callback.message.chat.id)
        chat_id = callback.message.chat.id
        try:
            _, subscription_id_str, page_str = callback.data.split(":")
            subscription_id = int(subscription_id_str)
            subscriptions, _ = await get_chat_subscriptions(chat_id, page=0, page_size=1000)
            sub_to_delete = next((sub for sub in subscriptions if sub['id'] == subscription_id), None)
            if not sub_to_delete: raise ValueError("Subscription not found in this chat")
            
            builder = InlineKeyboardBuilder().row(
                InlineKeyboardButton(text=translator.gettext(lang, "btn_confirm_delete"), callback_data=f"csub_del_confirm:{subscription_id}:{page_str}"),
                InlineKeyboardButton(text=translator.gettext(lang, "btn_cancel"), callback_data=f"csub_page:{page_str}")
            )
            await callback.message.edit_text(translator.gettext(lang, "subscription_confirm_delete", entity_name=sub_to_delete['entity_name']), reply_markup=builder.as_markup())
            await callback.answer()
        except (ValueError, IndexError):
            await callback.answer(translator.gettext(lang, "subscription_info_outdated"), show_alert=True)

    async def cq_confirm_delete_chat_subscription(self, callback: CallbackQuery, state: FSMContext):
        user_id, lang = callback.from_user.id, await translator.get_language(callback.from_user.id, callback.message.chat.id)
        try:
            _, subscription_id_str, page_str = callback.data.split(":")
            deleted_entity_name = await remove_schedule_subscription(int(subscription_id_str), user_id, is_chat_admin=True)
            if deleted_entity_name:
                await callback.answer(translator.gettext(lang, "subscription_removed", entity_name=deleted_entity_name))
                callback.data = f"csub_page:{page_str}"
                await self.cq_manage_chat_subscriptions(callback, state)
            else:
                await callback.answer(translator.gettext(lang, "subscription_info_outdated"), show_alert=True)
        except (ValueError, IndexError):
            await callback.answer(translator.gettext(lang, "subscription_info_outdated"), show_alert=True)

    # --- Short Name Management ---

    async def _get_short_names_keyboard(self, user_id: int, page: int = 0) -> tuple[InlineKeyboardBuilder, bool]:
        """Builds the keyboard for managing approved short names."""
        lang = await translator.get_language(user_id)
        page_size = 5 # Let's show 5 per page
        short_names, total_count = await get_all_short_names_with_ids(page=page, page_size=page_size)
        builder = InlineKeyboardBuilder()
        is_admin = user_id in ADMIN_USER_IDS

        # For default users, we need to know which names they have disabled
        disabled_ids = set()
        if not is_admin:
            disabled_ids = await get_disabled_short_names_for_user(user_id)

        for item in short_names:
            if is_admin:
                button_text = f"'{item['short_name']}' ⟵ '{item['full_name']}'"
                builder.row(
                    InlineKeyboardButton(text=button_text, callback_data="noop"),
                    InlineKeyboardButton(text=translator.gettext(lang, "btn_delete"), callback_data=f"sname_del:{item['id']}:{page}")
                )
            else: # Default user view
                is_disabled = item['id'] in disabled_ids
                status_emoji = "❌" if is_disabled else "✅"
                button_text = f"{status_emoji} '{item['short_name']}' ⟵ '{item['full_name']}'"
                builder.row(
                    InlineKeyboardButton(text=button_text, callback_data=f"sname_toggle:{item['id']}:{page}")
                )
        
        total_pages = (total_count + page_size - 1) // page_size
        if total_pages > 1:
            pagination_buttons = []
            if page > 0: pagination_buttons.append(InlineKeyboardButton(text=translator.gettext(lang, "pagination_back"), callback_data=f"sname_page:{page - 1}"))
            pagination_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
            if (page + 1) < total_pages: pagination_buttons.append(InlineKeyboardButton(text=translator.gettext(lang, "pagination_forward"), callback_data=f"sname_page:{page + 1}"))
            builder.row(*pagination_buttons)

        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "back_to_settings"), callback_data="back_to_settings"))
        return builder, total_count > 0

    async def cq_manage_short_names(self, callback: CallbackQuery, state: FSMContext):
        lang = await translator.get_language(callback.from_user.id)
        page = int(callback.data.split(":")[1]) if callback.data.startswith("sname_page:") else 0
        keyboard, has_items = await self._get_short_names_keyboard(callback.from_user.id, page=page)
        header_text = translator.gettext(lang, "short_names_management_header") if has_items else translator.gettext(lang, "short_names_list_empty")
        await callback.message.edit_text(header_text, reply_markup=keyboard.as_markup())
        await callback.answer()

    async def cq_delete_short_name(self, callback: CallbackQuery, state: FSMContext):
        lang = await translator.get_language(callback.from_user.id)
        _, short_name_id_str, page_str = callback.data.split(":")
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text=translator.gettext(lang, "btn_confirm_delete"), callback_data=f"sname_del_confirm:{short_name_id_str}:{page_str}"),
            InlineKeyboardButton(text=translator.gettext(lang, "btn_cancel"), callback_data=f"sname_page:{page_str}")
        )
        await callback.message.edit_text(translator.gettext(lang, "subscription_confirm_delete", entity_name="this short name"), reply_markup=builder.as_markup())
        await callback.answer()

    async def cq_confirm_delete_short_name(self, callback: CallbackQuery, state: FSMContext):
        _, short_name_id_str, page_str = callback.data.split(":")
        short_name_id = int(short_name_id_str)
        await delete_short_name_by_id(short_name_id)
        await callback.answer(translator.gettext(await translator.get_language(callback.from_user.id), "short_name_deleted_success"))
        # Refresh the menu
        callback.data = f"sname_page:{page_str}" # Mock the callback data to refresh the correct page
        await self.cq_manage_short_names(callback, state)

    async def cq_toggle_user_short_name(self, callback: CallbackQuery, state: FSMContext):
        """Handles enabling/disabling a short name for a default user."""
        user_id = callback.from_user.id
        _, short_name_id_str, page_str = callback.data.split(":")
        await toggle_short_name_for_user(user_id, int(short_name_id_str))
        await callback.answer()
        await self.cq_manage_short_names(callback, state) # Refresh the menu
        
    async def cq_sub_card(self, callback: CallbackQuery):
        sub_id = int(callback.data.split(":")[1])
        sub = await get_subscription_by_id(sub_id) # Нужно добавить этот метод в db, чтобы возвращал полный объект
        
        if not sub:
            await callback.answer("Подписка не найдена", show_alert=True)
            return await self.cq_subs_list(callback) # Вернуть в список

        # Формируем текст
        status_text = "Активна ✅" if sub['is_active'] else "Отключена ❌"
        time_str = sub['notification_time'].strftime("%H:%M")
        
        text = (
            f"📂 <b>Подписка: {sub['entity_name']}</b>\n\n"
            f"Статус: {status_text}\n"
            f"Уведомления: в {time_str}\n"
        )
        
        builder = InlineKeyboardBuilder()
        
        # Ряд 1: Вкл/Выкл | Время
        toggle_txt = "Выключить" if sub['is_active'] else "Включить"
        builder.row(
            InlineKeyboardButton(text=toggle_txt, callback_data=f"sub_toggle:{sub_id}"),
            InlineKeyboardButton(text="⏰ Время", callback_data=f"sub_time:{sub_id}")
        )
        
        # Ряд 2: Модули (Только для групп)
        if sub['entity_type'] == 'group':
            builder.row(InlineKeyboardButton(text="📚 Настроить модули", callback_data=f"sub_mods:{sub_id}"))
            
        # Ряд 3: Удалить
        builder.row(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"sub_del_ask:{sub_id}"))
        
        # Ряд 4: Назад
        builder.row(InlineKeyboardButton(text="⬅️ К списку", callback_data="manage_personal_subscriptions"))
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

    # 3. МЕНЮ МОДУЛЕЙ
    async def cq_sub_modules_menu(self, callback: CallbackQuery):
        sub_id = int(callback.data.split(":")[1])
        sub = await get_subscription_by_id(sub_id)
        
        await callback.answer("Загружаю список модулей...")
        
        # 1. Достаем расписание из кэша (или API если пусто)
        full_schedule = await get_cached_schedule(sub['entity_type'], sub['entity_id'])
        if not full_schedule:
            # TODO: Сделать fallback запрос к API здесь
            await callback.message.answer("Кэш пуст. Попробуйте обновить расписание через /schedule.")
            return

        # 2. Гибридный поиск модулей (Regex + Admin DB)
        available_modules = await get_unique_modules_hybrid(full_schedule)
        
        if not available_modules:
            await callback.answer("В этом расписании модули не найдены.", show_alert=True)
            return

        # 3. Текущие настройки
        selected = await get_subscription_modules(sub_id)
        if selected is None: selected = [] # None = пустой список для UI

        # 4. Клавиатура (используем ту же функцию из bot/keyboards.py)
        kb = get_modules_keyboard(available_modules, selected, sub_id)
        
        await callback.message.edit_text(
            f"Настройка модулей для <b>{sub['entity_name']}</b>:\n"
            "Отметьте галочками ✅ те модули, которые вы посещаете.",
            reply_markup=kb,
            parse_mode="HTML"
        )
        
    async def cq_subs_list(self, callback: CallbackQuery):
        """
        Отображает список подписок пользователя (только названия).
        При клике открывается карточка подписки.
        """
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id)
        
        # Получаем номер страницы из callback_data (если есть)
        page = 0
        if callback.data and "subs_page:" in callback.data:
            try:
                page = int(callback.data.split(":")[1])
            except (IndexError, ValueError):
                page = 0

        # Размер страницы - 5 подписок
        page_size = 5
        subs, total_count = await get_user_subscriptions(user_id, page=page, page_size=page_size)
        
        builder = InlineKeyboardBuilder()
        
        if not subs:
            text = translator.gettext(lang, "subscriptions_empty")
        else:
            text = translator.gettext(lang, "subscriptions_header")
            
            for sub in subs:
                # Формируем кнопку для перехода в карточку
                status_icon = "✅" if sub['is_active'] else "💤"
                # Обрезаем имя, если слишком длинное
                name = sub['entity_name'][:25] + "..." if len(sub['entity_name']) > 25 else sub['entity_name']
                button_text = f"{status_icon} {name}"
                
                # sub_open:{id} вызывает карточку подписки
                builder.row(InlineKeyboardButton(text=button_text, callback_data=f"sub_open:{sub['id']}"))

        # --- Пагинация ---
        total_pages = (total_count + page_size - 1) // page_size
        if total_pages > 1:
            pagination_buttons = []
            if page > 0:
                pagination_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"subs_page:{page - 1}"))
            
            pagination_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
            
            if page < total_pages - 1:
                pagination_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"subs_page:{page + 1}"))
            
            builder.row(*pagination_buttons)

        # Кнопка назад в главное меню настроек
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "back_to_settings"), callback_data="back_to_settings"))
        
        # Редактируем сообщение
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
        
    async def cq_sub_toggle(self, callback: CallbackQuery):
        """Переключает состояние подписки (Вкл/Выкл) и обновляет карточку."""
        user_id = callback.from_user.id
        try:
            sub_id = int(callback.data.split(":")[1])
            
            # Выполняем переключение в БД
            result = await toggle_subscription_status(sub_id, user_id, is_chat_admin=False)
            
            if result:
                # Если успешно, просто обновляем текущую карточку (она перерисуется с новым статусом)
                # Вызываем уже существующий метод cq_sub_card
                # Важно: подменяем data, так как cq_sub_card ожидает "sub_open:ID"
                callback.data = f"sub_open:{sub_id}" 
                await self.cq_sub_card(callback)
            else:
                await callback.answer("Ошибка: подписка не найдена или нет прав.", show_alert=True)
                
        except (ValueError, IndexError):
            await callback.answer("Некорректные данные.", show_alert=True)

    async def cq_sub_delete_ask(self, callback: CallbackQuery):
        """Спрашивает подтверждение перед удалением."""
        try:
            sub_id = int(callback.data.split(":")[1])
            sub = await get_subscription_by_id(sub_id)
            
            if not sub:
                await callback.answer("Подписка не найдена", show_alert=True)
                return

            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"sub_del_confirm:{sub_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"sub_open:{sub_id}") # Возврат в карточку
            )
            
            await callback.message.edit_text(
                f"Вы уверены, что хотите удалить подписку на <b>{sub['entity_name']}</b>?", 
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
            await callback.answer()
        except ValueError:
            await callback.answer("Ошибка данных.", show_alert=True)

    async def cq_sub_delete_confirm(self, callback: CallbackQuery):
        """Удаляет подписку и возвращает в общий список."""
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id)
        try:
            sub_id = int(callback.data.split(":")[1])
            deleted_name = await remove_schedule_subscription(sub_id, user_id, is_chat_admin=False)
            
            if deleted_name:
                await callback.answer(f"Подписка '{deleted_name}' удалена.")
                # Возвращаемся в список подписок
                await self.cq_subs_list(callback)
            else:
                await callback.answer(translator.gettext(lang, "subscription_info_outdated"), show_alert=True)
                
        except ValueError:
            await callback.answer("Ошибка данных.", show_alert=True)

    async def cq_sub_time(self, callback: CallbackQuery, state: FSMContext):
        """Запрашивает новое время для уведомлений."""
        user_id = callback.from_user.id
        lang = await translator.get_language(user_id)
        try:
            sub_id = int(callback.data.split(":")[1])
            
            # Устанавливаем состояние ожидания ввода
            await state.set_state(SettingsStates.awaiting_new_sub_time)
            
            # Сохраняем контекст, чтобы обработчик текста знал, что обновлять
            # Добавляем original_chat_id, чтобы потом можно было вернуться
            await state.update_data(
                sub_id=sub_id, 
                is_chat_admin=False,
                original_chat_id=callback.message.chat.id,
                original_message_id=callback.message.message_id,
                # page нужен для совместимости со старым кодом, ставим 0
                page=0 
            )
            
            # Кнопка отмены, которая возвращает обратно в карточку подписки
            builder = InlineKeyboardBuilder()
            builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data=f"sub_open:{sub_id}"))
            
            await callback.message.edit_text(
                translator.gettext(lang, "subscription_change_time_prompt"),
                reply_markup=builder.as_markup()
            )
            await callback.answer()
            
        except ValueError:
            await callback.answer("Ошибка данных.", show_alert=True)
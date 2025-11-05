from aiogram import F, Router
from aiogram.filters import Command, and_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, Message, CallbackQuery
from types import SimpleNamespace
import re, datetime

from shared_lib.database import get_user_settings, get_user_repos, update_user_settings_db, get_user_subscriptions, remove_schedule_subscription, get_chat_subscriptions, toggle_subscription_status, update_subscription_notification_time, get_chat_settings, update_chat_settings_db
from shared_lib.i18n import translator
from .schedule import ScheduleManager
from .admin import AdminOrCreatorFilter


AVAILABLE_LANGUAGES = {"en": "English", "ru": "Русский"}
MD_DISPLAY_MODES = ['md_file', 'html_file', 'pdf_file']
SUBSCRIPTIONS_PER_PAGE = 5

class SettingsStates(StatesGroup):
    awaiting_new_sub_time = State()

class SettingsManager:
    def __init__(self, schedule_manager: ScheduleManager):
        self.router = Router()
        self.schedule_manager = schedule_manager
        self._register_handlers()
        self.AVAILABLE_LANGUAGES = AVAILABLE_LANGUAGES

    def _register_handlers(self):
        # Main settings entry points for private and group chats
        self.router.message(Command('settings'), F.chat.type == "private")(self.command_settings_private)
        self.router.message(Command('settings'), F.chat.type.in_({"group", "supergroup"}), AdminOrCreatorFilter())(self.command_settings_group)

        self.router.callback_query(F.data == "back_to_settings")(self.cq_back_to_settings)

        # Display settings
        self.router.callback_query(F.data == "settings_toggle_docstring")(self.cq_toggle_docstring)
        self.router.callback_query(F.data == "settings_cycle_md_mode")(self.cq_cycle_md_mode)

        # Language settings
        self.router.callback_query(F.data == "settings_cycle_language")(self.cq_cycle_language)

        # LaTeX settings
        self.router.callback_query(F.data.startswith("latex_padding_"))(self.cq_change_latex_padding)
        self.router.callback_query(F.data.startswith("latex_dpi_"))(self.cq_change_latex_dpi)

        # Subscription management
        # Personal subscriptions
        self.router.callback_query(F.data == "manage_personal_subscriptions")(self.cq_manage_personal_subscriptions)
        self.router.callback_query(F.data.startswith("psub_page:"))(self.cq_manage_personal_subscriptions)
        self.router.callback_query(F.data.startswith("psub_toggle:"))(self.cq_toggle_personal_subscription)
        self.router.callback_query(F.data.startswith("psub_del:"))(self.cq_delete_personal_subscription_prompt)
        self.router.callback_query(F.data.startswith("psub_del_confirm:"))(self.cq_confirm_delete_personal_subscription)
        self.router.callback_query(F.data.startswith("psub_time:"))(self.cq_change_personal_subscription_time_prompt)

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

    async def get_settings_keyboard(self, user_id: int) -> InlineKeyboardBuilder:
        """Creates the main inline keyboard for user settings."""
        settings = await get_user_settings(user_id)
        lang = settings.get('language', 'en')
        builder = InlineKeyboardBuilder()

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

        # LaTeX settings
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

        # GitHub Repositories
        user_repos = await get_user_repos(user_id)
        repo_button_key = "settings_manage_repos_btn" if user_repos else "settings_add_repos_btn"
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, repo_button_key), callback_data="manage_repos"))

        # Language Setting
        current_lang_name = AVAILABLE_LANGUAGES.get(lang, "Unknown")
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "settings_language_btn", lang_name=current_lang_name), callback_data="settings_cycle_language"))

        # Schedule Subscriptions
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "settings_manage_subscriptions_btn"), callback_data="manage_personal_subscriptions"))

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
            button_text = f"{status_emoji} {sub['entity_name']} ({sub['notification_time']}) -> {target_label}"
            
            toggle_button_text = translator.gettext(lang, "btn_disable") if sub['is_active'] else translator.gettext(lang, "btn_enable")
            builder.row(
                InlineKeyboardButton(text=button_text, callback_data="noop"),
                InlineKeyboardButton(text=toggle_button_text, callback_data=f"psub_toggle:{sub['id']}:{page}"),
                InlineKeyboardButton(text="⏰", callback_data=f"psub_time:{sub['id']}:{page}"),
                InlineKeyboardButton(text=translator.gettext(lang, "btn_delete"), callback_data=f"psub_del:{sub['id']}:{page}")
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
                InlineKeyboardButton(text="⏰", callback_data=f"csub_time:{sub['id']}:{page}"),
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
            await state.set_state(SettingsStates.awaiting_new_sub_time)
            await state.update_data(sub_id=int(subscription_id_str), page=int(page_str), is_chat_admin=False)
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

    async def process_new_subscription_time(self, message: Message, state: FSMContext):
        user_id, lang = message.from_user.id, await translator.get_language(message.from_user.id, message.chat.id)
        time_str = message.text.strip()

        if not re.match(r"^\d{1,2}:\d{2}$", time_str):
            await message.reply(translator.gettext(lang, "schedule_invalid_time_format"))
            return
        
        try:
            new_time = datetime.datetime.strptime(time_str, "%H:%M").time()
            state_data = await state.get_data()
            sub_id, page, is_chat_admin = state_data['sub_id'], state_data['page'], state_data['is_chat_admin']
            
            updated_entity_name = await update_subscription_notification_time(sub_id, new_time, user_id, is_chat_admin)
            
            if updated_entity_name:
                await message.answer(translator.gettext(lang, "subscription_time_updated", entity_name=updated_entity_name, time_str=time_str))
                # Create a mock object that mimics a CallbackQuery to refresh the menu.
                # This is necessary because the target handlers expect a CallbackQuery object, not a Message.
                mock_callback = SimpleNamespace(
                    message=message,  # The handler will access callback.message
                    from_user=message.from_user,
                    data=f"psub_page:{page}" if not is_chat_admin else f"csub_page:{page}"
                )
                if is_chat_admin: await self.cq_manage_chat_subscriptions(mock_callback, state)
                else: await self.cq_manage_personal_subscriptions(mock_callback, state)
            else:
                await message.answer(translator.gettext(lang, "subscription_info_outdated"))
        except ValueError:
            await message.reply(translator.gettext(lang, "schedule_invalid_time_value"))
        finally:
            await state.clear()

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
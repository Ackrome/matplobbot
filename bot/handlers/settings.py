from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from shared_lib.database import get_user_settings, get_user_repos, update_user_settings_db, get_user_subscriptions, remove_schedule_subscription
from shared_lib.i18n import translator
from .schedule import ScheduleManager


AVAILABLE_LANGUAGES = {"en": "English", "ru": "Русский"}
MD_DISPLAY_MODES = ['md_file', 'html_file', 'pdf_file']
SUBSCRIPTIONS_PER_PAGE = 5

class SettingsManager:
    def __init__(self, schedule_manager: ScheduleManager):
        self.router = Router()
        self.schedule_manager = schedule_manager
        self._register_handlers()

    def _register_handlers(self):
        # Main settings entry points
        self.router.message(Command('settings'))(self.command_settings)
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
        self.router.callback_query(F.data == "manage_subscriptions")(self.cq_manage_subscriptions)
        self.router.callback_query(F.data.startswith("sub_page:"))(self.cq_manage_subscriptions)
        self.router.callback_query(F.data.startswith("sub_del:"))(self.cq_delete_subscription_prompt)
        self.router.callback_query(F.data.startswith("sub_del_confirm:"))(self.cq_confirm_delete_subscription)

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
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "settings_manage_subscriptions_btn"), callback_data="manage_subscriptions"))

        return builder

    async def command_settings(self, message: Message):
        user_id = message.from_user.id
        lang = await translator.get_user_language(user_id)
        keyboard = await self.get_settings_keyboard(user_id)
        await message.answer(translator.gettext(lang, "settings_menu_header"), reply_markup=keyboard.as_markup())

    async def cq_back_to_settings(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = await translator.get_user_language(user_id)
        keyboard = await self.get_settings_keyboard(user_id)
        await callback.message.edit_text(translator.gettext(lang, "settings_menu_header"), reply_markup=keyboard.as_markup())
        await callback.answer()

    async def cq_toggle_docstring(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = await translator.get_user_language(user_id)
        settings = await get_user_settings(user_id)
        settings['show_docstring'] = not settings['show_docstring']
        await update_user_settings_db(user_id, settings)
        keyboard = await self.get_settings_keyboard(user_id)
        await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
        await callback.answer(translator.gettext(lang, "settings_docstring_updated"))

    async def cq_cycle_md_mode(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = await translator.get_user_language(user_id)
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
        md_mode_map = {'md_file': 'settings_md_mode_md', 'html_file': 'settings_md_mode_html', 'pdf_file': 'settings_md_mode_pdf'}
        mode_text = translator.gettext(lang, md_mode_map.get(new_mode, 'settings_md_mode_unknown'))
        await callback.answer(translator.gettext(lang, "settings_md_mode_updated", mode_text=mode_text))

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
        await update_user_settings_db(user_id, settings)
        keyboard = await self.get_settings_keyboard(user_id)
        await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
        await callback.answer(translator.gettext(new_lang, "settings_language_updated", lang_name=AVAILABLE_LANGUAGES[new_lang]))

    async def cq_change_latex_padding(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = await translator.get_user_language(user_id)
        settings = await get_user_settings(user_id)
        current_padding = settings['latex_padding']
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
        lang = await translator.get_user_language(user_id)
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

    async def get_subscriptions_keyboard(self, user_id: int, page: int = 0) -> InlineKeyboardBuilder:
        lang = await translator.get_user_language(user_id)
        subscriptions, total_count = await get_user_subscriptions(user_id, page=page, page_size=SUBSCRIPTIONS_PER_PAGE)
        builder = InlineKeyboardBuilder()
        for sub in subscriptions:
            builder.row(
                InlineKeyboardButton(text=f"🔔 {sub['entity_name']} ({sub['notification_time']})", callback_data="noop"),
                InlineKeyboardButton(text=translator.gettext(lang, "favorites_remove_btn"), callback_data=f"sub_del:{sub['id']}:{page}")
            )
        total_pages = (total_count + SUBSCRIPTIONS_PER_PAGE - 1) // SUBSCRIPTIONS_PER_PAGE
        if total_pages > 1:
            pagination_buttons = []
            if page > 0: pagination_buttons.append(InlineKeyboardButton(text=translator.gettext(lang, "pagination_back"), callback_data=f"sub_page:{page - 1}"))
            pagination_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
            if (page + 1) < total_pages: pagination_buttons.append(InlineKeyboardButton(text=translator.gettext(lang, "pagination_forward"), callback_data=f"sub_page:{page + 1}"))
            builder.row(*pagination_buttons)
        builder.row(InlineKeyboardButton(text=translator.gettext(lang, "back_to_settings"), callback_data="back_to_settings"))
        return builder

    async def cq_manage_subscriptions(self, callback: CallbackQuery, state: FSMContext):
        user_id = callback.from_user.id
        lang = await translator.get_user_language(user_id)
        page = int(callback.data.split(":")[1]) if callback.data.startswith("sub_page:") else 0
        _, total_count = await get_user_subscriptions(user_id, page=page, page_size=SUBSCRIPTIONS_PER_PAGE)
        header_text = translator.gettext(lang, "subscriptions_header") if total_count > 0 else translator.gettext(lang, "subscriptions_empty")
        keyboard = await self.get_subscriptions_keyboard(user_id, page=page)
        await callback.message.edit_text(header_text, reply_markup=keyboard.as_markup())
        await callback.answer()

    async def cq_delete_subscription_prompt(self, callback: CallbackQuery):
        user_id, lang = callback.from_user.id, await translator.get_user_language(callback.from_user.id)
        try:
            _, subscription_id_str, page_str = callback.data.split(":")
            subscription_id = int(subscription_id_str)
            subscriptions, _ = await get_user_subscriptions(user_id, page=0, page_size=1000)
            sub_to_delete = next((sub for sub in subscriptions if sub['id'] == subscription_id), None)
            if not sub_to_delete: raise ValueError("Subscription not found")
            builder = InlineKeyboardBuilder().row(
                InlineKeyboardButton(text=translator.gettext(lang, "btn_confirm_delete"), callback_data=f"sub_del_confirm:{subscription_id}:{page_str}"),
                InlineKeyboardButton(text=translator.gettext(lang, "btn_cancel_delete"), callback_data=f"sub_page:{page_str}")
            )
            await callback.message.edit_text(translator.gettext(lang, "subscription_confirm_delete", entity_name=sub_to_delete['entity_name']), reply_markup=builder.as_markup())
            await callback.answer()
        except (ValueError, IndexError):
            await callback.answer(translator.gettext(lang, "subscription_info_outdated"), show_alert=True)

    async def cq_confirm_delete_subscription(self, callback: CallbackQuery, state: FSMContext):
        user_id, lang = callback.from_user.id, await translator.get_user_language(callback.from_user.id)
        try:
            _, subscription_id_str, page_str = callback.data.split(":")
            deleted_entity_name = await remove_schedule_subscription(int(subscription_id_str), user_id)
            if deleted_entity_name:
                await callback.answer(translator.gettext(lang, "subscription_removed", entity_name=deleted_entity_name))
                callback.data = f"sub_page:{page_str}"
                await self.cq_manage_subscriptions(callback, state)
            else:
                await callback.answer(translator.gettext(lang, "subscription_info_outdated"), show_alert=True)
        except (ValueError, IndexError):
            await callback.answer(translator.gettext(lang, "subscription_info_outdated"), show_alert=True)
from collections.abc import Collection, Mapping

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from shared_lib.database import get_user_repos, get_user_settings
from shared_lib.i18n import translator


class SettingsKeyboardFactory:
    """Build the private settings keyboard without owning Telegram handlers."""

    def __init__(
        self,
        *,
        available_languages: Mapping[str, str],
        admin_user_ids: Collection[int],
    ) -> None:
        self.available_languages = available_languages
        self.admin_user_ids = admin_user_ids

    async def build_display(
        self,
        builder: InlineKeyboardBuilder,
        settings: dict,
        lang: str,
    ) -> None:
        toggles = (
            ("use_short_names", True, "settings_use_short_names", "settings_toggle_short_names"),
            (
                "show_schedule_emojis",
                True,
                "settings_show_schedule_emojis",
                "settings_toggle_emojis",
            ),
            (
                "show_lecturer_emails",
                True,
                "settings_show_lecturer_emails",
                "settings_toggle_emails",
            ),
            ("show_docstring", True, "settings_show_docstring", "settings_toggle_docstring"),
        )
        for setting_key, default, label_key, callback_data in toggles:
            status_key = (
                "settings_docstring_on"
                if settings.get(setting_key, default)
                else "settings_docstring_off"
            )
            builder.row(
                InlineKeyboardButton(
                    text=translator.gettext(
                        lang,
                        label_key,
                        status=translator.gettext(lang, status_key),
                    ),
                    callback_data=callback_data,
                )
            )

        md_mode = settings.get("md_display_mode", "md_file")
        md_mode_map = {
            "md_file": translator.gettext(lang, "settings_md_mode_md"),
            "html_file": translator.gettext(lang, "settings_md_mode_html"),
            "pdf_file": translator.gettext(lang, "settings_md_mode_pdf"),
        }
        builder.row(
            InlineKeyboardButton(
                text=translator.gettext(
                    lang,
                    "settings_md_display_mode",
                    mode_text=md_mode_map.get(
                        md_mode,
                        translator.gettext(lang, "settings_md_mode_unknown"),
                    ),
                ),
                callback_data="settings_cycle_md_mode",
            )
        )

        details_status_key = (
            "settings_docstring_on"
            if settings.get("show_module_details", True)
            else "settings_docstring_off"
        )
        builder.row(
            InlineKeyboardButton(
                text=translator.gettext(
                    lang,
                    "settings_show_module_details",
                    status=translator.gettext(lang, details_status_key),
                ),
                callback_data="settings_toggle_module_details",
            )
        )

    async def build_latex(
        self,
        builder: InlineKeyboardBuilder,
        settings: dict,
        lang: str,
    ) -> None:
        builder.row(
            InlineKeyboardButton(text="➖", callback_data="latex_padding_decr"),
            InlineKeyboardButton(
                text=translator.gettext(
                    lang,
                    "settings_latex_padding",
                    padding=settings["latex_padding"],
                ),
                callback_data="noop",
            ),
            InlineKeyboardButton(text="➕", callback_data="latex_padding_incr"),
        )
        builder.row(
            InlineKeyboardButton(text="➖", callback_data="latex_dpi_decr"),
            InlineKeyboardButton(
                text=translator.gettext(
                    lang,
                    "settings_latex_dpi",
                    dpi=settings["latex_dpi"],
                ),
                callback_data="noop",
            ),
            InlineKeyboardButton(text="➕", callback_data="latex_dpi_incr"),
        )

    async def build_data_management(
        self,
        builder: InlineKeyboardBuilder,
        user_id: int,
        lang: str,
    ) -> None:
        user_repos = await get_user_repos(user_id)
        repo_button_key = "settings_manage_repos_btn" if user_repos else "settings_add_repos_btn"
        buttons = (
            (repo_button_key, "manage_repos"),
            ("settings_manage_subscriptions_btn", "manage_personal_subscriptions"),
            ("settings_manage_short_names_btn", "manage_short_names"),
            ("settings_delete_my_data_btn", "delete_my_data"),
        )
        for label_key, callback_data in buttons:
            builder.row(
                InlineKeyboardButton(
                    text=translator.gettext(lang, label_key),
                    callback_data=callback_data,
                )
            )

    async def build_admin(
        self,
        builder: InlineKeyboardBuilder,
        settings: dict,
        lang: str,
    ) -> None:
        summary_time = settings.get("admin_daily_summary_time", "09:00")
        builder.row(
            InlineKeyboardButton(
                text=translator.gettext(
                    lang,
                    "admin_settings_summary_time_btn",
                    time=summary_time,
                ),
                callback_data="admin_settings_summary_time",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=translator.gettext(lang, "admin_get_summary_now_btn"),
                callback_data="admin_get_summary_now",
            )
        )
        summary_days = settings.get("admin_summary_days", [0, 1, 2, 3, 4])
        day_names = translator.gettext(lang, "calendar_days_short").split(",")
        builder.row(
            *[
                InlineKeyboardButton(
                    text=f"{'✅' if index in summary_days else '❌'} {day_name}",
                    callback_data=f"admin_toggle_summary_day:{index}",
                )
                for index, day_name in enumerate(day_names)
            ]
        )

    async def build(self, user_id: int) -> InlineKeyboardBuilder:
        settings = await get_user_settings(user_id)
        lang = settings.get("language", "en")
        builder = InlineKeyboardBuilder()

        await self.build_display(builder, settings, lang)
        await self.build_latex(builder, settings, lang)
        await self.build_data_management(builder, user_id, lang)

        current_lang_name = self.available_languages.get(lang, "Unknown")
        builder.row(
            InlineKeyboardButton(
                text=translator.gettext(
                    lang,
                    "settings_language_btn",
                    lang_name=current_lang_name,
                ),
                callback_data="settings_cycle_language",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=translator.gettext(lang, "settings_restart_onboarding_btn"),
                callback_data="restart_onboarding",
            )
        )

        if user_id in self.admin_user_ids:
            await self.build_admin(builder, settings, lang)

        return builder

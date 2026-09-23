import unittest
from unittest.mock import AsyncMock, patch

SHARED_DB_AVAILABLE = True
try:
    from bot.services import settings_keyboard
    from bot.services.myschedule_filters import MyScheduleFilterService
    from shared_lib import database as shared_database
except ModuleNotFoundError:
    SHARED_DB_AVAILABLE = False


@unittest.skipUnless(
    SHARED_DB_AVAILABLE, "database dependencies are not installed in this environment"
)
class TestMyScheduleFiltersSettings(unittest.IsolatedAsyncioTestCase):
    async def test_extracted_builtin_filter_presets_preserve_behavior(self):
        active_subscriptions = [
            {"id": 1, "entity_type": "group"},
            {"id": 2, "entity_type": "auditorium"},
        ]

        self.assertEqual(
            MyScheduleFilterService.build_builtin("all", active_subscriptions),
            {"excluded_subs": [], "excluded_types": []},
        )
        self.assertEqual(
            MyScheduleFilterService.build_builtin("hide_auditoriums", active_subscriptions),
            {"excluded_subs": [2], "excluded_types": []},
        )
        self.assertIsNone(MyScheduleFilterService.build_builtin("unknown", active_subscriptions))

    async def test_extracted_settings_keyboard_keeps_registered_callback_contract(self):
        factory = settings_keyboard.SettingsKeyboardFactory(
            available_languages={"en": "English", "ru": "Русский"},
            admin_user_ids={42},
        )
        user_settings = {
            "language": "en",
            "show_docstring": True,
            "latex_padding": 15,
            "latex_dpi": 300,
        }
        with (
            patch.object(
                settings_keyboard,
                "get_user_settings",
                new=AsyncMock(return_value=user_settings),
            ),
            patch.object(
                settings_keyboard,
                "get_user_repos",
                new=AsyncMock(return_value=[]),
            ),
        ):
            builder = await factory.build(42)

        callback_values = {
            button.callback_data
            for row in builder.as_markup().inline_keyboard
            for button in row
            if button.callback_data
        }
        self.assertIn("settings_toggle_short_names", callback_values)
        self.assertIn("manage_personal_subscriptions", callback_values)
        self.assertIn("admin_settings_summary_time", callback_values)

    async def test_normalize_filters_sanitizes_values(self):
        normalized = shared_database.normalize_myschedule_filters(
            {
                "excluded_subs": ["1", 2, "abc", None, 2],
                "excluded_types": ["Lecture", "Other", "DROP", "", "Lecture"],
            }
        )
        self.assertEqual(normalized["excluded_subs"], [1, 2])
        self.assertEqual(normalized["excluded_types"], ["Lecture", "Other"])

    async def test_normalize_filters_keeps_consultation_type(self):
        normalized = shared_database.normalize_myschedule_filters(
            {
                "excluded_subs": [],
                "excluded_types": ["Consultation", "DROP", "Consultation"],
            }
        )
        self.assertEqual(normalized["excluded_types"], ["Consultation"])

    async def test_get_user_myschedule_filters_uses_defaults(self):
        with patch.object(
            shared_database,
            "get_user_settings",
            new=AsyncMock(return_value={"language": "en"}),
        ):
            filters = await shared_database.get_user_myschedule_filters(42)
        self.assertEqual(filters, {"excluded_subs": [], "excluded_types": []})

    async def test_save_user_myschedule_filters_persists_normalized_payload(self):
        fake_settings = {
            "language": "en",
            "myschedule_filters": {"excluded_subs": [], "excluded_types": []},
        }
        with (
            patch.object(
                shared_database,
                "get_user_settings",
                new=AsyncMock(return_value=fake_settings),
            ),
            patch.object(
                shared_database,
                "update_user_settings_db",
                new=AsyncMock(return_value=None),
            ) as mocked_update,
        ):
            saved = await shared_database.save_user_myschedule_filters(
                42,
                {
                    "excluded_subs": ["10", "invalid"],
                    "excluded_types": ["Seminar", "DROP"],
                },
            )

        self.assertEqual(saved, {"excluded_subs": [10], "excluded_types": ["Seminar"]})
        mocked_update.assert_awaited_once()
        args = mocked_update.await_args.args
        self.assertEqual(args[0], 42)
        self.assertEqual(
            args[1]["myschedule_filters"],
            {"excluded_subs": [10], "excluded_types": ["Seminar"]},
        )

    async def test_normalize_myschedule_filter_presets_sanitizes_values(self):
        normalized = shared_database.normalize_myschedule_filter_presets(
            [
                {
                    "id": "abc123",
                    "name": "  Exams only  ",
                    "filters": {
                        "excluded_subs": ["1", "bad", 2],
                        "excluded_types": ["Lecture", "Other", "DROP"],
                    },
                    "created_at": "2026-04-10T10:00:00+00:00",
                    "updated_at": "2026-04-10T10:00:01+00:00",
                },
                {"id": "", "name": "invalid", "filters": {}},
            ]
        )

        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["id"], "abc123")
        self.assertEqual(normalized[0]["name"], "Exams only")
        self.assertEqual(normalized[0]["filters"]["excluded_subs"], [1, 2])
        self.assertEqual(normalized[0]["filters"]["excluded_types"], ["Lecture", "Other"])

    async def test_save_user_myschedule_filter_preset_persists_normalized_payload(self):
        fake_settings = {
            "language": "en",
            "myschedule_filter_presets": [],
        }
        with (
            patch.object(
                shared_database,
                "get_user_settings",
                new=AsyncMock(return_value=fake_settings),
            ),
            patch.object(
                shared_database,
                "update_user_settings_db",
                new=AsyncMock(return_value=None),
            ) as mocked_update,
        ):
            saved = await shared_database.save_user_myschedule_filter_preset(
                42,
                "Week Exams",
                {"excluded_subs": ["7", "bad"], "excluded_types": ["Lecture", "DROP"]},
            )

        self.assertEqual(saved["name"], "Week Exams")
        self.assertEqual(saved["filters"], {"excluded_subs": [7], "excluded_types": ["Lecture"]})
        mocked_update.assert_awaited_once()
        args = mocked_update.await_args.args
        self.assertEqual(args[0], 42)
        self.assertEqual(len(args[1]["myschedule_filter_presets"]), 1)
        self.assertEqual(
            args[1]["myschedule_filter_presets"][0]["filters"],
            {"excluded_subs": [7], "excluded_types": ["Lecture"]},
        )

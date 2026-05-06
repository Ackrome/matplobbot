import unittest
from unittest.mock import AsyncMock, patch

SHARED_DB_AVAILABLE = True
try:
    from shared_lib import database as shared_database
except ModuleNotFoundError:
    SHARED_DB_AVAILABLE = False


@unittest.skipUnless(
    SHARED_DB_AVAILABLE, "database dependencies are not installed in this environment"
)
class TestMyScheduleFiltersSettings(unittest.IsolatedAsyncioTestCase):
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

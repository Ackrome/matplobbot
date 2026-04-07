import unittest
from unittest.mock import AsyncMock, patch

SHARED_DB_AVAILABLE = True
try:
    from shared_lib import database as shared_database
except ModuleNotFoundError:
    SHARED_DB_AVAILABLE = False


@unittest.skipUnless(SHARED_DB_AVAILABLE, "database dependencies are not installed in this environment")
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

    async def test_get_user_myschedule_filters_uses_defaults(self):
        with patch.object(
            shared_database,
            "get_user_settings",
            new=AsyncMock(return_value={"language": "en"}),
        ):
            filters = await shared_database.get_user_myschedule_filters(42)
        self.assertEqual(filters, {"excluded_subs": [], "excluded_types": []})

    async def test_save_user_myschedule_filters_persists_normalized_payload(self):
        fake_settings = {"language": "en", "myschedule_filters": {"excluded_subs": [], "excluded_types": []}}
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

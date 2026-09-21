import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bot.logger import _avatar_cache, _get_avatar_pic_url
from fastapi_stats_app.routers import stats_router
from shared_lib.database import (
    get_leaderboard_data_from_db,
    get_user_profile_data_from_db,
)
from shared_lib.models import User


class TestAvatarSecurity(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _avatar_cache.clear()
        stats_router._avatar_image_cache.clear()

    async def test_bot_logger_does_not_leak_bot_token(self):
        fake_bot = MagicMock()
        fake_bot.token = "SECRET_BOT_TOKEN_12345"

        photo_mock = MagicMock()
        photo_mock.file_id = "photo_123"
        user_photos_mock = MagicMock()
        user_photos_mock.photos = [[photo_mock]]

        fake_bot.get_user_profile_photos = AsyncMock(return_value=user_photos_mock)

        avatar_url = await _get_avatar_pic_url(fake_bot, 999)

        self.assertIsNotNone(avatar_url)
        self.assertNotIn("SECRET_BOT_TOKEN_12345", avatar_url)
        self.assertNotIn("api.telegram.org/file/bot", avatar_url)
        self.assertEqual(avatar_url, "/api/stats/users/999/avatar")

    async def test_leaderboard_scrubs_leaked_bot_token(self):
        fake_session = AsyncMock()
        fake_row = MagicMock()
        fake_mapping = {
            "user_id": 42,
            "full_name": "Test User",
            "username": "testuser",
            "avatar_pic_url": "https://api.telegram.org/file/bot987654:ABCDEF/photos/file_0.jpg",
            "actions_count": 10,
            "last_action_time": "2026-09-17 12:00:00",
        }
        fake_row._mapping = fake_mapping

        result_mock = MagicMock()
        result_mock.__iter__.return_value = [fake_row]
        fake_session.execute.return_value = result_mock

        data = await get_leaderboard_data_from_db(fake_session)

        self.assertEqual(len(data), 1)
        self.assertNotIn("bot987654:ABCDEF", data[0]["avatar_pic_url"])
        self.assertEqual(data[0]["avatar_pic_url"], "/api/stats/users/42/avatar")

    async def test_user_profile_scrubs_leaked_bot_token(self):
        fake_session = AsyncMock()
        fake_user = User(
            user_id=77,
            full_name="Profile User",
            username="profuser",
            avatar_pic_url="https://api.telegram.org/file/botSUPERSECRET/photos/pic.jpg",
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = fake_user

        count_result = MagicMock()
        count_result.scalar.return_value = 5

        actions_result = MagicMock()
        actions_result.__iter__.return_value = []

        fake_session.execute.side_effect = [user_result, count_result, actions_result]

        data = await get_user_profile_data_from_db(fake_session, user_id=77)

        self.assertIsNotNone(data)
        avatar_url = data["user_details"]["avatar_pic_url"]
        self.assertNotIn("SUPERSECRET", avatar_url)
        self.assertEqual(avatar_url, "/api/stats/users/77/avatar")

    async def test_avatar_proxy_uses_shared_http_configuration(self):
        class FakeDb:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def scalar(self, _query):
                return 42

        class FakeResponse:
            def __init__(self, payload=None, body=b"avatar"):
                self.status = 200
                self.payload = payload
                self.body = body

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def json(self):
                return self.payload

            async def read(self):
                return self.body

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            def get(self, url, **_kwargs):
                if url.endswith("getUserProfilePhotos"):
                    return FakeResponse({"result": {"photos": [[{"file_id": "file-1"}]]}})
                if url.endswith("getFile"):
                    return FakeResponse({"result": {"file_path": "photos/avatar.jpg"}})
                return FakeResponse(body=b"jpeg")

        with (
            patch.object(stats_router, "get_session", return_value=FakeDb()),
            patch.object(stats_router.aiohttp, "ClientSession", return_value=FakeSession()),
            patch.object(stats_router, "BOT_TOKEN", "server-only-token"),
        ):
            response = await stats_router.get_user_avatar(42)

        self.assertEqual(response.media_type, "image/jpeg")
        self.assertEqual(response.body, b"jpeg")


if __name__ == "__main__":
    unittest.main()

import logging
import unittest
from unittest.mock import AsyncMock, patch

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage

from shared_lib.telegram_polling import run_polling_with_retry


class _FakeFSMRedis:
    def __init__(self):
        self.values = {}
        self.expirations = {}

    async def set(self, key, value, *, ex=None, **_kwargs):
        self.values[key] = value
        self.expirations[key] = ex
        return True

    async def get(self, key):
        return self.values.get(key)

    async def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
            self.expirations.pop(key, None)
        return len(keys)


class TestTelegramPolling(unittest.IsolatedAsyncioTestCase):
    async def test_run_polling_with_retry_retries_retryable_errors(self):
        start_polling = AsyncMock(side_effect=[OSError("proxy reset"), None])

        with patch("shared_lib.telegram_polling.asyncio.sleep", new=AsyncMock()) as mocked_sleep:
            await run_polling_with_retry(
                start_polling,
                retry_delay_seconds=5,
                logger=logging.getLogger("test.telegram_polling"),
                retryable_exceptions=(OSError,),
            )

        self.assertEqual(start_polling.await_count, 2)
        mocked_sleep.assert_awaited_once_with(5)

    async def test_run_polling_with_retry_propagates_non_retryable_errors(self):
        start_polling = AsyncMock(side_effect=ValueError("boom"))

        with (
            patch("shared_lib.telegram_polling.asyncio.sleep", new=AsyncMock()) as mocked_sleep,
            self.assertRaises(ValueError),
        ):
            await run_polling_with_retry(
                start_polling,
                retry_delay_seconds=5,
                logger=logging.getLogger("test.telegram_polling"),
                retryable_exceptions=(OSError,),
            )

        mocked_sleep.assert_not_awaited()

    async def test_redis_fsm_state_survives_storage_recreation_and_clear(self):
        redis_backend = _FakeFSMRedis()
        key_builder = DefaultKeyBuilder(prefix="matplobbot:fsm", with_bot_id=True)
        storage_before_restart = RedisStorage(
            redis=redis_backend,
            key_builder=key_builder,
            state_ttl=60,
            data_ttl=60,
        )
        storage_after_restart = RedisStorage(
            redis=redis_backend,
            key_builder=key_builder,
            state_ttl=60,
            data_ttl=60,
        )
        storage_key = StorageKey(bot_id=10, chat_id=20, user_id=30)

        await storage_before_restart.set_state(storage_key, "MailSetup:waiting_password")
        await storage_before_restart.set_data(storage_key, {"email": "user@example.com"})

        self.assertEqual(
            await storage_after_restart.get_state(storage_key),
            "MailSetup:waiting_password",
        )
        self.assertEqual(
            await storage_after_restart.get_data(storage_key),
            {"email": "user@example.com"},
        )
        self.assertTrue(redis_backend.expirations)
        self.assertEqual(set(redis_backend.expirations.values()), {60})

        await FSMContext(storage=storage_after_restart, key=storage_key).clear()
        self.assertIsNone(await storage_before_restart.get_state(storage_key))
        self.assertEqual(await storage_before_restart.get_data(storage_key), {})

    async def test_bot_builds_namespaced_fsm_storage_from_shared_url(self):
        from bot import main as bot_main

        sentinel_storage = object()
        with (
            patch.object(bot_main, "FSM_TTL_SECONDS", 3600),
            patch.object(bot_main, "get_redis_url", return_value="rediss://:pw@redis:6380/5"),
            patch.object(
                bot_main.RedisStorage,
                "from_url",
                return_value=sentinel_storage,
            ) as from_url,
        ):
            result = bot_main.create_fsm_storage()

        self.assertIs(result, sentinel_storage)
        args, kwargs = from_url.call_args
        self.assertEqual(args[0], "rediss://:pw@redis:6380/5")
        self.assertEqual(kwargs["state_ttl"], 3600)
        self.assertEqual(kwargs["data_ttl"], 3600)
        self.assertEqual(kwargs["key_builder"].prefix, "matplobbot:fsm")
        self.assertTrue(kwargs["key_builder"].with_bot_id)

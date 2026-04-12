import logging
import unittest
from unittest.mock import AsyncMock, patch

from shared_lib.telegram_polling import run_polling_with_retry


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

        with patch("shared_lib.telegram_polling.asyncio.sleep", new=AsyncMock()) as mocked_sleep:
            with self.assertRaises(ValueError):
                await run_polling_with_retry(
                    start_polling,
                    retry_delay_seconds=5,
                    logger=logging.getLogger("test.telegram_polling"),
                    retryable_exceptions=(OSError,),
                )

        mocked_sleep.assert_not_awaited()

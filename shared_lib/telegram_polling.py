import asyncio
import logging
from collections.abc import Awaitable, Callable


async def run_polling_with_retry(
    start_polling: Callable[[], Awaitable[None]],
    *,
    retry_delay_seconds: float,
    logger: logging.Logger,
    retryable_exceptions: tuple[type[Exception], ...],
) -> None:
    while True:
        try:
            await start_polling()
            return
        except asyncio.CancelledError:
            raise
        except retryable_exceptions as exc:
            logger.warning(
                "Bot polling failed with a retryable network error. Restarting in %.1f seconds.",
                retry_delay_seconds,
                exc_info=exc,
            )
            await asyncio.sleep(retry_delay_seconds)

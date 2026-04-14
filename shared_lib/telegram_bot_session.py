import asyncio
import logging
import os
from typing import Any, cast

import aiohttp
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import TelegramMethod
from aiogram.methods.base import TelegramType
from aiohttp import ClientError

from shared_lib.telegram_http import get_telegram_proxy_recheck_url, normalize_proxy_url

logger = logging.getLogger(__name__)


def _read_retry_attempts(value: str | None, default: int) -> int:
    try:
        return max(0, int((value or "").strip() or default))
    except (TypeError, ValueError):
        return default


def _read_retry_delay_seconds(value: str | None, default: float) -> float:
    try:
        return max(0.0, float((value or "").strip() or default))
    except (TypeError, ValueError):
        return default


class TelegramBotSession(AiohttpSession):
    def __init__(
        self,
        proxy_url: str | None = None,
        limit: int = 100,
        *,
        request_retry_attempts: int | None = None,
        request_retry_delay_seconds: float | None = None,
        **kwargs: Any,
    ) -> None:
        self._request_kwargs: dict[str, Any] = {}
        self._proxy_recheck_url = get_telegram_proxy_recheck_url(proxy_url)
        self._request_retry_attempts = (
            request_retry_attempts
            if request_retry_attempts is not None
            else _read_retry_attempts(os.getenv("TELEGRAM_REQUEST_RETRY_ATTEMPTS"), 1)
        )
        self._request_retry_delay_seconds = (
            request_retry_delay_seconds
            if request_retry_delay_seconds is not None
            else _read_retry_delay_seconds(os.getenv("TELEGRAM_REQUEST_RETRY_DELAY_SECONDS"), 0.5)
        )
        self._socks_proxy_url = None

        normalized_proxy_url = normalize_proxy_url(proxy_url)

        kwargs.pop("connector", None)
        super().__init__(limit=limit, **kwargs)

        if not normalized_proxy_url:
            return

        if normalized_proxy_url.startswith("socks"):
            self._socks_proxy_url = normalized_proxy_url
        else:
            self._request_kwargs["proxy"] = normalized_proxy_url

    async def create_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            session_kwargs = getattr(self, "_session_kwargs", {})
            if self._socks_proxy_url:
                from aiohttp_socks import ProxyConnector

                connector = ProxyConnector.from_url(self._socks_proxy_url)
                self._session = aiohttp.ClientSession(
                    connector=connector,
                    json_serialize=self.json_dumps,
                    timeout=self.timeout,
                    **session_kwargs,
                )
            else:
                self._session = aiohttp.ClientSession(
                    json_serialize=self.json_dumps, timeout=self.timeout, **session_kwargs
                )
        return self._session

    async def make_request(
        self, bot, method: TelegramMethod[TelegramType], timeout: int | None = None
    ) -> TelegramType:
        session = await self.create_session()
        url = self.api.api_url(token=bot.token, method=method.__api_method__)
        form = self.build_form_data(bot=bot, method=method)
        request_timeout = self.timeout if timeout is None else timeout

        for attempt in range(self._request_retry_attempts + 1):
            response_started = False
            try:
                async with session.post(
                    url,
                    data=form,
                    timeout=request_timeout,
                    **self._request_kwargs,
                ) as resp:
                    response_started = True
                    raw_result = await resp.text()
            except TimeoutError:
                if attempt < self._request_retry_attempts and not response_started:
                    await self._sleep_before_retry(method, attempt + 1)
                    continue
                raise TelegramNetworkError(method=method, message="Request timeout error")
            except (ClientError, OSError) as exc:
                if attempt < self._request_retry_attempts and not response_started:
                    await self._sleep_before_retry(method, attempt + 1, exc)
                    continue
                raise TelegramNetworkError(method=method, message=f"{type(exc).__name__}: {exc}")

            response = self.check_response(
                bot=bot, method=method, status_code=resp.status, content=raw_result
            )
            return cast(TelegramType, response.result)

        raise TelegramNetworkError(method=method, message="Telegram request exhausted retry loop.")

    async def _sleep_before_retry(
        self,
        method: TelegramMethod[TelegramType],
        attempt_number: int,
        exc: Exception | None = None,
    ) -> None:
        logger.warning(
            "Retrying Telegram request %s after transport error (%s/%s): %s",
            method.__api_method__,
            attempt_number,
            self._request_retry_attempts,
            type(exc).__name__ if exc is not None else "TimeoutError",
        )
        await self._trigger_proxy_recheck()
        if self._request_retry_delay_seconds > 0:
            await asyncio.sleep(self._request_retry_delay_seconds)

    async def _trigger_proxy_recheck(self) -> None:
        if not self._proxy_recheck_url:
            return
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self._proxy_recheck_url):
                    pass
        except Exception:
            pass

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ):
        if headers is None:
            headers = {}
        session = await self.create_session()
        async with session.get(
            url,
            timeout=timeout,
            headers=headers,
            raise_for_status=raise_for_status,
            **self._request_kwargs,
        ) as resp:
            async for chunk in resp.content.iter_chunked(chunk_size):
                yield chunk
from typing import Any, cast

from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import TelegramMethod
from aiogram.methods.base import TelegramType
from aiohttp import ClientError

from shared_lib.telegram_http import normalize_proxy_url


class TelegramBotSession(AiohttpSession):
    """Aiogram session that uses native aiohttp HTTP proxy support when possible."""

    def __init__(self, proxy_url: str | None = None, limit: int = 100, **kwargs: Any) -> None:
        self._request_kwargs: dict[str, Any] = {}
        normalized_proxy_url = normalize_proxy_url(proxy_url)
        super().__init__(limit=limit, **kwargs)

        if not normalized_proxy_url:
            return

        if normalized_proxy_url.startswith("socks"):
            self._setup_proxy_connector(normalized_proxy_url)
        else:
            self._request_kwargs["proxy"] = normalized_proxy_url

    async def make_request(
        self, bot, method: TelegramMethod[TelegramType], timeout: int | None = None
    ) -> TelegramType:
        session = await self.create_session()
        url = self.api.api_url(token=bot.token, method=method.__api_method__)
        form = self.build_form_data(bot=bot, method=method)

        try:
            async with session.post(
                url,
                data=form,
                timeout=self.timeout if timeout is None else timeout,
                **self._request_kwargs,
            ) as resp:
                raw_result = await resp.text()
        except TimeoutError:
            raise TelegramNetworkError(method=method, message="Request timeout error")
        except ClientError as exc:
            raise TelegramNetworkError(method=method, message=f"{type(exc).__name__}: {exc}")

        response = self.check_response(
            bot=bot, method=method, status_code=resp.status, content=raw_result
        )
        return cast(TelegramType, response.result)

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

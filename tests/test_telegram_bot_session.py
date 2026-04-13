import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiohttp import ClientConnectionError, ClientOSError, TCPConnector

from shared_lib.telegram_bot_session import TelegramBotSession


class TestTelegramBotSession(unittest.TestCase):
    def test_http_proxy_uses_native_request_proxy(self):
        session = TelegramBotSession(proxy_url="http://proxy:20170")

        self.assertEqual(session._request_kwargs, {"proxy": "http://proxy:20170"})
        self.assertIs(session._connector_type, TCPConnector)

    def test_no_proxy_has_no_request_proxy(self):
        session = TelegramBotSession(proxy_url=None)

        self.assertEqual(session._request_kwargs, {})

    def test_retry_settings_use_safe_defaults(self):
        session = TelegramBotSession(proxy_url=None)

        self.assertEqual(session._request_retry_attempts, 1)
        self.assertEqual(session._request_retry_delay_seconds, 0.5)


class _FakeResponse:
    def __init__(self, *, text_value="{}", text_exc=None, status=200):
        self.status = status
        self._text_value = text_value
        self._text_exc = text_exc

    async def text(self):
        if self._text_exc is not None:
            raise self._text_exc
        return self._text_value


class _FakeRequestContextManager:
    def __init__(self, *, response=None, enter_exc=None):
        self._response = response
        self._enter_exc = enter_exc

    async def __aenter__(self):
        if self._enter_exc is not None:
            raise self._enter_exc
        return self._response

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeClientSession:
    def __init__(self, contexts):
        self._contexts = list(contexts)
        self.calls = 0

    def post(self, *args, **kwargs):
        self.calls += 1
        return self._contexts.pop(0)


class TestTelegramBotSessionRetries(unittest.IsolatedAsyncioTestCase):
    async def test_retries_transport_error_before_response_starts(self):
        session = TelegramBotSession(
            proxy_url=None,
            request_retry_attempts=1,
            request_retry_delay_seconds=0,
        )
        fake_session = _FakeClientSession(
            [
                _FakeRequestContextManager(enter_exc=ClientConnectionError("proxy reset")),
                _FakeRequestContextManager(response=_FakeResponse(text_value='{"ok":true}')),
            ]
        )

        session.create_session = AsyncMock(return_value=fake_session)
        session.api = SimpleNamespace(
            api_url=lambda token, method: f"https://example.test/{method}"
        )
        session.build_form_data = Mock(return_value={"chat_id": "1"})
        session.check_response = Mock(return_value=SimpleNamespace(result={"ok": True}))
        session._trigger_proxy_recheck = AsyncMock()

        result = await session.make_request(
            bot=SimpleNamespace(token="token"),
            method=SimpleNamespace(__api_method__="sendMessage"),
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(fake_session.calls, 2)
        session._trigger_proxy_recheck.assert_awaited_once()

    async def test_does_not_retry_after_response_has_started(self):
        session = TelegramBotSession(
            proxy_url=None,
            request_retry_attempts=1,
            request_retry_delay_seconds=0,
        )
        fake_session = _FakeClientSession(
            [
                _FakeRequestContextManager(
                    response=_FakeResponse(text_exc=ClientOSError(54, "connection reset"))
                )
            ]
        )

        session.create_session = AsyncMock(return_value=fake_session)
        session.api = SimpleNamespace(
            api_url=lambda token, method: f"https://example.test/{method}"
        )
        session.build_form_data = Mock(return_value={"chat_id": "1"})
        session.check_response = Mock(return_value=SimpleNamespace(result={"ok": True}))
        session._trigger_proxy_recheck = AsyncMock()

        with self.assertRaisesRegex(Exception, "ClientOSError"):
            await session.make_request(
                bot=SimpleNamespace(token="token"),
                method=SimpleNamespace(__api_method__="sendMessage"),
            )

        self.assertEqual(fake_session.calls, 1)
        session._trigger_proxy_recheck.assert_not_awaited()

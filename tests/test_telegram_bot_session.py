import unittest

from aiohttp import TCPConnector

from shared_lib.telegram_bot_session import TelegramBotSession


class TestTelegramBotSession(unittest.TestCase):
    def test_http_proxy_uses_native_request_proxy(self):
        session = TelegramBotSession(proxy_url="http://proxy:20170")

        self.assertEqual(session._request_kwargs, {"proxy": "http://proxy:20170"})
        self.assertIs(session._connector_type, TCPConnector)

    def test_no_proxy_has_no_request_proxy(self):
        session = TelegramBotSession(proxy_url=None)

        self.assertEqual(session._request_kwargs, {})

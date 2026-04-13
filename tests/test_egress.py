import os
import unittest
from unittest.mock import patch

from shared_lib.egress import (
    configure_process_http_proxy_env,
    get_global_http_proxy_url,
    get_telegram_proxy_transport,
    get_telegram_proxy_url,
)
from shared_lib.telegram_http import get_telegram_proxy_recheck_url


class TestEgressConfig(unittest.TestCase):
    def test_telegram_proxy_transport_defaults_to_auto(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_telegram_proxy_transport(), "auto")

    def test_telegram_proxy_transport_accepts_tcp_alias(self):
        with patch.dict(os.environ, {"TELEGRAM_PROXY_TRANSPORT": "tcp"}, clear=True):
            self.assertEqual(get_telegram_proxy_transport(), "socks")

    def test_telegram_proxy_prefers_dedicated_variable(self):
        with patch.dict(
            os.environ,
            {"TELEGRAM_PROXY_URL": "socks5://telegram:20170", "PROXY_URL": "socks5://legacy:20170"},
            clear=True,
        ):
            self.assertEqual(get_telegram_proxy_url(), "socks5://telegram:20170")

    def test_telegram_proxy_uses_http_for_local_mixed_proxy_service(self):
        with patch.dict(
            os.environ,
            {"TELEGRAM_PROXY_URL": "socks5://proxy:20170"},
            clear=True,
        ):
            self.assertEqual(get_telegram_proxy_url(), "http://proxy:20170")

    def test_telegram_proxy_transport_can_force_socks_for_local_proxy_service(self):
        with patch.dict(
            os.environ,
            {
                "TELEGRAM_PROXY_URL": "socks5://proxy:20170",
                "TELEGRAM_PROXY_TRANSPORT": "socks",
            },
            clear=True,
        ):
            self.assertEqual(get_telegram_proxy_url(), "socks5://proxy:20170")

    def test_telegram_proxy_transport_can_force_http_for_non_local_proxy_service(self):
        with patch.dict(
            os.environ,
            {
                "TELEGRAM_PROXY_URL": "socks5://edge-proxy:20170",
                "TELEGRAM_PROXY_TRANSPORT": "http",
            },
            clear=True,
        ):
            self.assertEqual(get_telegram_proxy_url(), "http://edge-proxy:20170")

    def test_global_proxy_falls_back_to_legacy_variable(self):
        with patch.dict(os.environ, {"PROXY_URL": "socks5://legacy:20170"}, clear=True):
            self.assertEqual(get_global_http_proxy_url(), "socks5://legacy:20170")

    def test_telegram_proxy_recheck_url_defaults_for_local_proxy_service(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                get_telegram_proxy_recheck_url("socks5://proxy:20170"),
                "http://proxy:8080/recheck?group=telegram",
            )

    def test_telegram_proxy_recheck_url_prefers_explicit_env(self):
        with patch.dict(
            os.environ,
            {"TELEGRAM_PROXY_RECHECK_URL": "http://proxy:8080/recheck?group=all"},
            clear=True,
        ):
            self.assertEqual(
                get_telegram_proxy_recheck_url("socks5://proxy:20170"),
                "http://proxy:8080/recheck?group=all",
            )

    def test_configure_process_http_proxy_env_sets_no_proxy_and_socks5h(self):
        with patch.dict(os.environ, {"NO_PROXY": "localhost"}, clear=True):
            configure_process_http_proxy_env(
                "socks5://proxy:20170",
                no_proxy_hosts=("ruz.fa.ru",),
            )

            self.assertEqual(os.environ["HTTP_PROXY"], "socks5h://proxy:20170")
            self.assertEqual(os.environ["HTTPS_PROXY"], "socks5h://proxy:20170")
            self.assertEqual(os.environ["ALL_PROXY"], "socks5h://proxy:20170")
            self.assertEqual(os.environ["NO_PROXY"], "localhost,ruz.fa.ru")
            self.assertEqual(os.environ["no_proxy"], "localhost,ruz.fa.ru")

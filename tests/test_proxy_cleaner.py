import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from proxy.proxy_cleaner import (
    _build_group_summary,
    build_outline_mihomo_yaml,
    build_summary_payload,
    load_or_build_provider_yaml,
    load_subscription_urls,
    merge_proxy_yaml_documents,
    parse_outline_ss_uri,
    process_outline_dynamic_payload,
    process_something_json,
    process_subscription_payload,
    process_uri_subscription,
    write_cached_provider_yaml,
)


class TestProxyCleaner(unittest.TestCase):
    def test_parse_outline_ss_uri_supports_plain_userinfo(self):
        parsed = parse_outline_ss_uri(
            "ss://chacha20-ietf-poly1305:secret@example.com:8388/?outline=1"
        )

        self.assertEqual(parsed["server"], "example.com")
        self.assertEqual(parsed["server_port"], 8388)
        self.assertEqual(parsed["method"], "chacha20-ietf-poly1305")
        self.assertEqual(parsed["password"], "secret")

    def test_process_outline_dynamic_payload_supports_nested_access_key(self):
        rendered = process_outline_dynamic_payload(
            json.dumps(
                {
                    "name": "Outline",
                    "accessKey": "ss://Y2hhY2hhMjAtaWV0Zi1wb2x5MTMwNTpzZWNyZXQ=@example.com:8388/?outline=1",
                }
            )
        )

        self.assertIsNotNone(rendered)
        self.assertIn("type: ss", rendered)
        self.assertIn('server: "example.com"', rendered)
        self.assertIn('cipher: "chacha20-ietf-poly1305"', rendered)
        self.assertIn('password: "secret"', rendered)

    def test_build_outline_mihomo_yaml_includes_optional_prefix(self):
        rendered = build_outline_mihomo_yaml(
            {
                "server": "example.com",
                "server_port": 8388,
                "method": "chacha20-ietf-poly1305",
                "password": "secret",
                "prefix": "hello",
            },
            name="outline",
        )

        self.assertIn('prefix: "hello"', rendered)

    def test_build_outline_mihomo_yaml_escapes_control_characters(self):
        rendered = build_outline_mihomo_yaml(
            {
                "server": "example.com",
                "server_port": 8388,
                "method": "chacha20-ietf-poly1305",
                "password": "secret",
                "prefix": "GET / HTTP/1.1\r\nHost: example.com\r\n",
            },
            name="outline",
        )

        self.assertIn('prefix: "GET / HTTP/1.1\\r\\nHost: example.com\\r\\n"', rendered)

    def test_merge_proxy_yaml_documents_combines_outline_and_subscription(self):
        outline_yaml = build_outline_mihomo_yaml(
            {
                "server": "outline.example.com",
                "server_port": 8388,
                "method": "chacha20-ietf-poly1305",
                "password": "secret",
            },
            name="outline",
        )
        sub_yaml = process_something_json(
            json.dumps(
                [
                    {
                        "remarks": "Happ node",
                        "outbounds": [
                            {
                                "protocol": "vless",
                                "settings": {
                                    "vnext": [
                                        {
                                            "address": "edge.example.com",
                                            "port": 443,
                                            "users": [{"id": "uuid-123"}],
                                        }
                                    ]
                                },
                                "streamSettings": {"network": "tcp", "security": "tls"},
                            }
                        ],
                    }
                ]
            )
        )

        rendered = merge_proxy_yaml_documents(outline_yaml, sub_yaml)

        self.assertIsNotNone(rendered)
        self.assertIn('server: "outline.example.com"', rendered)
        self.assertIn('server: "edge.example.com"', rendered)
        self.assertEqual(rendered.count("  - name:"), 2)

    def test_process_something_json_preserves_reality_tls_fields(self):
        raw = json.dumps(
            [
                {
                    "remarks": "Happ node",
                    "outbounds": [
                        {
                            "protocol": "socks",
                            "tag": "provider-chain",
                            "settings": {
                                "servers": [
                                    {
                                        "address": "127.0.0.2",
                                        "port": 1080,
                                        "users": [{"user": "u", "pass": "p"}],
                                    }
                                ]
                            },
                        },
                        {
                            "protocol": "vless",
                            "settings": {
                                "vnext": [
                                    {
                                        "address": "edge.example.com",
                                        "port": 443,
                                        "users": [
                                            {
                                                "id": "uuid-123",
                                                "flow": "xtls-rprx-vision",
                                                "encryption": "",
                                            }
                                        ],
                                    }
                                ]
                            },
                            "streamSettings": {
                                "network": "tcp",
                                "security": "reality",
                                "packetEncoding": "xudp",
                                "sockopt": {"dialerProxy": "provider-chain"},
                                "tlsSettings": {
                                    "serverName": "cdn.example.com",
                                    "alpn": ["h2", "http/1.1"],
                                    "allowInsecure": True,
                                },
                                "realitySettings": {
                                    "fingerprint": "chrome",
                                    "publicKey": "pubkey-123",
                                    "shortId": "abcd1234",
                                },
                            },
                        },
                    ],
                }
            ]
        )

        rendered = process_something_json(raw)

        self.assertIsNotNone(rendered)
        self.assertIn("type: socks5", rendered)
        self.assertIn("type: vless", rendered)
        self.assertIn('flow: "xtls-rprx-vision"', rendered)
        self.assertIn('packet-encoding: "xudp"', rendered)
        self.assertIn('servername: "cdn.example.com"', rendered)
        self.assertIn("skip-cert-verify: true", rendered)
        self.assertIn('client-fingerprint: "chrome"', rendered)
        self.assertIn('public-key: "pubkey-123"', rendered)
        self.assertIn('short-id: "abcd1234"', rendered)
        self.assertIn('dialer-proxy: "json-0-0-provider-chain"', rendered)
        self.assertIn("alpn:", rendered)

    def test_process_something_json_preserves_all_supported_outbounds(self):
        raw = json.dumps(
            [
                {
                    "remarks": "Combined profile",
                    "outbounds": [
                        {
                            "protocol": "vless",
                            "settings": {
                                "vnext": [
                                    {
                                        "address": "first.example.com",
                                        "port": 443,
                                        "users": [{"id": "uuid-first"}],
                                    }
                                ]
                            },
                            "streamSettings": {
                                "network": "xhttp",
                                "security": "tls",
                                "xhttpSettings": {
                                    "path": "/xhttp",
                                    "host": "cdn.example.com",
                                    "mode": "packet-up",
                                    "extra": {
                                        "xPaddingObfsMode": True,
                                        "sessionPlacement": "path",
                                        "xmux": {"maxConnections": "1-2"},
                                    },
                                },
                                "tlsSettings": {"serverName": "cdn.example.com"},
                            },
                        },
                        {
                            "protocol": "vless",
                            "settings": {
                                "vnext": [
                                    {
                                        "address": "second.example.com",
                                        "port": 8443,
                                        "users": [{"id": "uuid-second"}],
                                    }
                                ]
                            },
                            "streamSettings": {"network": "tcp", "security": "reality"},
                        },
                        {
                            "protocol": "hysteria",
                            "settings": {"address": "hy2.example.com", "port": 443, "version": 2},
                            "streamSettings": {
                                "network": "hysteria",
                                "security": "tls",
                                "hysteriaSettings": {"auth": "hy2-password", "version": 2},
                                "tlsSettings": {
                                    "serverName": "hy2.example.com",
                                    "alpn": ["h3"],
                                },
                            },
                        },
                        {
                            "protocol": "shadowsocks",
                            "settings": {
                                "servers": [
                                    {
                                        "address": "ss.example.com",
                                        "port": 8388,
                                        "method": "chacha20-ietf-poly1305",
                                        "password": "ss-password",
                                        "uot": True,
                                        "UoTVersion": 2,
                                    }
                                ]
                            },
                        },
                    ],
                }
            ]
        )

        rendered = process_something_json(raw, name_prefix="source")

        self.assertIsNotNone(rendered)
        self.assertEqual(rendered.count("  - name:"), 4)
        self.assertEqual(rendered.count("type: vless"), 2)
        self.assertIn("type: hysteria2", rendered)
        self.assertIn("type: ss", rendered)
        self.assertIn("xhttp-opts:", rendered)
        self.assertIn("x-padding-obfs-mode: true", rendered)
        self.assertIn('session-placement: "path"', rendered)
        self.assertIn('max-connections: "1-2"', rendered)
        self.assertIn("udp-over-tcp: true", rendered)
        self.assertIn("udp-over-tcp-version: 2", rendered)

    def test_subscription_url_file_extends_legacy_url_without_duplicates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "subscriptions.json"
            path.write_text(
                json.dumps(
                    {
                        "urls": [
                            "https://one.example/sub",
                            "https://two.example/sub",
                            "https://one.example/sub",
                            "file:///not-allowed",
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.dict(os.environ, {"SUB_URL": "https://legacy.example/sub"}),
                patch("proxy.proxy_cleaner.SUB_URLS_FILE", str(path)),
            ):
                urls = load_subscription_urls()

        self.assertEqual(
            urls,
            [
                "https://legacy.example/sub",
                "https://one.example/sub",
                "https://two.example/sub",
            ],
        )

    def test_stale_provider_cache_is_served_before_background_refresh(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "provider.yaml"
            with (
                patch("proxy.proxy_cleaner.CACHE_FILE", str(cache_path)),
                patch("proxy.proxy_cleaner.start_background_refresh") as start_refresh,
                patch("proxy.proxy_cleaner.build_combined_provider_yaml") as build_provider,
            ):
                write_cached_provider_yaml('proxies:\n  - name: "cached"')
                os.utime(cache_path, (0, 0))
                rendered = load_or_build_provider_yaml()

        self.assertIn('name: "cached"', rendered)
        start_refresh.assert_called_once_with()
        build_provider.assert_not_called()

    def test_uri_subscription_supports_mixed_happ_protocols(self):
        vmess_payload = json.dumps(
            {
                "v": "2",
                "ps": "VMess",
                "add": "vmess.example.com",
                "port": "443",
                "id": "00000000-0000-0000-0000-000000000001",
                "aid": "0",
                "scy": "auto",
                "net": "ws",
                "host": "cdn.example.com",
                "path": "/ws",
                "tls": "tls",
                "sni": "cdn.example.com",
            }
        )
        import base64

        vmess = base64.urlsafe_b64encode(vmess_payload.encode()).decode().rstrip("=")
        raw = "\n".join(
            [
                "vless://00000000-0000-0000-0000-000000000002@vless.example.com:443?security=reality&type=xhttp&mode=stream-up&path=%2Fx&sni=cover.example.com&pbk=public-key&sid=abcd&extra=%7B%22xmux%22%3A%7B%22maxConnections%22%3A1%2C%22cMaxReuseTimes%22%3A0%7D%7D#VLESS",
                "trojan://secret@trojan.example.com:443?security=tls&type=grpc&serviceName=svc&sni=trojan.example.com#Trojan",
                f"vmess://{vmess}",
                "ss://chacha20-ietf-poly1305:secret@ss.example.com:8388?plugin=v2ray-plugin%3Bmode%3Dwebsocket%3Bmux%3D0#SS",
                "hysteria2://secret@hy2.example.com:443?sni=hy2.example.com&obfs=salamander&obfs-password=obfs#HY2",
                "tuic://00000000-0000-0000-0000-000000000003:secret@tuic.example.com:443?sni=tuic.example.com&udp_relay_mode=native#TUIC",
                "anytls://secret@anytls.example.com:443?sni=anytls.example.com#AnyTLS",
                "hysteria://hysteria.example.com:443?auth=secret&protocol=udp&upmbps=20&downmbps=50#Hysteria",
                "mierus://user:secret@mieru.example.com?port=2999&protocol=TCP&multiplexing=MULTIPLEXING_LOW#Mieru",
                "naive://user:secret@naive.example.com:443#Unsupported",
            ]
        )

        rendered, details = process_uri_subscription(raw, name_prefix="test")

        self.assertIsNotNone(rendered)
        for proxy_type in (
            "vless",
            "trojan",
            "vmess",
            "ss",
            "hysteria2",
            "tuic",
            "anytls",
            "hysteria",
            "mieru",
        ):
            self.assertIn(f"type: {proxy_type}", rendered)
        self.assertIn("reuse-settings:", rendered)
        self.assertIn("max-connections: 1", rendered)
        self.assertIn("c-max-reuse-times: 0", rendered)
        self.assertIn("mux: false", rendered)
        self.assertEqual(details["unsupported_protocols"], {"naive": 1})

    def test_base64_uri_subscription_is_decoded_locally(self):
        import base64

        uri = "vless://00000000-0000-0000-0000-000000000004@example.com:443?security=tls#Node"
        encoded = base64.urlsafe_b64encode(uri.encode()).decode()

        rendered, details = process_subscription_payload(encoded, name_prefix="encoded")

        self.assertIsNotNone(rendered)
        self.assertIn("type: vless", rendered)
        self.assertEqual(details["valid_nodes"], 1)

    def test_direct_yaml_normalizes_json_surrogate_pairs_for_mihomo(self):
        raw = r"""proxies:
  - name: "Legacy node"
    type: ss
    server: "example.com"
    port: 8388
    cipher: "chacha20-ietf-poly1305"
    password: "secret"
    plugin: "obfs-local"
    plugin-opts:
      obfs-host: "example.com/\ud83c\udde8"
"""

        rendered, details = process_subscription_payload(raw, name_prefix="legacy")

        self.assertNotIn(r"\ud83c", rendered.lower())
        self.assertIn("\U0001f1e8", rendered)
        self.assertEqual(yaml.safe_load(rendered)["proxies"][0]["type"], "ss")
        self.assertEqual(yaml.safe_load(rendered)["proxies"][0]["plugin"], "obfs")
        self.assertIn("host", yaml.safe_load(rendered)["proxies"][0]["plugin-opts"])
        self.assertEqual(details["valid_nodes"], 1)

    def test_build_group_summary_sorts_candidates_by_delay(self):
        group_snapshot = {"now": "node-b", "all": ["node-a", "node-b", "node-c"]}
        proxy_index = {
            "node-a": {"name": "node-a", "delay": 250, "alive": True},
            "node-b": {"name": "node-b", "delay": 120, "alive": True},
            "node-c": {"name": "node-c", "alive": False},
        }

        summary = _build_group_summary("TELEGRAM-AUTO", group_snapshot, proxy_index)

        self.assertEqual(summary["selected"], "node-b")
        self.assertEqual(summary["candidate_count"], 3)
        self.assertEqual(
            [item["name"] for item in summary["top_candidates"]],
            ["node-b", "node-a", "node-c"],
        )

    def test_build_summary_payload_uses_controller_snapshot(self):
        fake_snapshot = {
            "telegram_group": {"now": "node-a", "all": ["node-a"]},
            "openai_group": {"now": "node-b", "all": ["node-b"]},
            "providers": {
                "something-telegram": {"proxies": [{"name": "node-a", "delay": 90, "alive": True}]},
                "something-openai": {"proxies": [{"name": "node-b", "delay": 140, "alive": True}]},
            },
        }

        from unittest.mock import patch

        import proxy.proxy_cleaner as proxy_cleaner

        proxy_cleaner.STATE["last_build"] = {"merged_entries": 2}
        with patch.object(proxy_cleaner, "build_controller_snapshot", return_value=fake_snapshot):
            summary = build_summary_payload()

        self.assertEqual(summary["telegram"]["selected"], "node-a")
        self.assertEqual(summary["telegram"]["top_candidates"][0]["delay"], 90)
        self.assertEqual(summary["openai"]["selected"], "node-b")

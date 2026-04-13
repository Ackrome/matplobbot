import json
import unittest

from proxy.proxy_cleaner import (
    _build_group_summary,
    build_outline_mihomo_yaml,
    build_summary_payload,
    merge_proxy_yaml_documents,
    parse_outline_ss_uri,
    process_outline_dynamic_payload,
    process_something_json,
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
        self.assertIn('dialer-proxy: "provider-chain"', rendered)
        self.assertIn("alpn:", rendered)

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
                "something-telegram": {
                    "proxies": [{"name": "node-a", "delay": 90, "alive": True}]
                },
                "something-openai": {
                    "proxies": [{"name": "node-b", "delay": 140, "alive": True}]
                },
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

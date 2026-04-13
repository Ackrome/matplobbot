import json
import unittest

from proxy.proxy_cleaner import process_something_json


class TestProxyCleaner(unittest.TestCase):
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
        self.assertIn("flow: 'xtls-rprx-vision'", rendered)
        self.assertIn("packet-encoding: 'xudp'", rendered)
        self.assertIn("servername: 'cdn.example.com'", rendered)
        self.assertIn("skip-cert-verify: true", rendered)
        self.assertIn("client-fingerprint: 'chrome'", rendered)
        self.assertIn("public-key: 'pubkey-123'", rendered)
        self.assertIn("short-id: 'abcd1234'", rendered)
        self.assertIn("dialer-proxy: 'provider-chain'", rendered)
        self.assertIn("alpn:", rendered)

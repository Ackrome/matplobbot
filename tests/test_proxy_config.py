import unittest
from pathlib import Path

import yaml

PROXY_CONFIG = Path("proxy/proxy_config.yaml").read_text(encoding="utf-8")


class TestProxyConfig(unittest.TestCase):
    def test_proxy_config_uses_domain_specific_groups(self):
        self.assertIn('name: "TELEGRAM-AUTO"', PROXY_CONFIG)
        self.assertIn('name: "OPENAI-AUTO"', PROXY_CONFIG)
        self.assertIn("type: url-test", PROXY_CONFIG)
        self.assertIn("tolerance: 100", PROXY_CONFIG)
        self.assertIn("max-failed-times: 1", PROXY_CONFIG)
        self.assertIn("lazy: false", PROXY_CONFIG)

    def test_proxy_config_routes_only_target_domains_through_proxy(self):
        self.assertIn("DOMAIN,api.telegram.org,TELEGRAM-AUTO", PROXY_CONFIG)
        self.assertIn("DOMAIN-SUFFIX,telegram.org,TELEGRAM-AUTO", PROXY_CONFIG)
        self.assertIn("DOMAIN-SUFFIX,chatgpt.com,OPENAI-AUTO", PROXY_CONFIG)
        self.assertIn("DOMAIN-SUFFIX,openai.com,OPENAI-AUTO", PROXY_CONFIG)
        self.assertIn("DOMAIN-SUFFIX,ruz.fa.ru,DIRECT", PROXY_CONFIG)
        self.assertIn("MATCH,DIRECT", PROXY_CONFIG)

    def test_proxy_config_does_not_fall_back_to_catch_all_proxying(self):
        self.assertNotIn("MATCH, AUTO-BEST-NODE", PROXY_CONFIG)
        self.assertNotIn('name: "AUTO-BEST-NODE"', PROXY_CONFIG)

    def test_each_provider_probes_its_real_destination(self):
        config = yaml.safe_load(PROXY_CONFIG)
        providers = config["proxy-providers"]

        self.assertEqual(
            providers["something-telegram"]["health-check"]["url"],
            "https://api.telegram.org",
        )
        self.assertEqual(providers["something-telegram"]["health-check"]["interval"], 300)
        self.assertEqual(
            providers["something-openai"]["health-check"]["url"],
            "https://api.openai.com/v1/models",
        )
        self.assertEqual(providers["something-openai"]["health-check"]["interval"], 300)

        groups = {group["name"]: group for group in config["proxy-groups"]}
        self.assertEqual(groups["TELEGRAM-AUTO"]["interval"], 60)
        self.assertEqual(groups["OPENAI-AUTO"]["interval"], 60)

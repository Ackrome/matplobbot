import json
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path

# `shared_lib.i18n` imports database helpers from `shared_lib.database`,
# which depends on SQLAlchemy. For this unit test we only need Translator
# fallback logic, so we provide a lightweight stub module.
fake_database_module = types.ModuleType("shared_lib.database")


async def _fake_get_settings(*_args, **_kwargs):
    return {}


fake_database_module.get_chat_settings = _fake_get_settings
fake_database_module.get_user_settings = _fake_get_settings
sys.modules.setdefault("shared_lib.database", fake_database_module)

from shared_lib.i18n import Translator


class TestLocalizationCompleteness(unittest.TestCase):
    def test_ru_and_en_locale_key_sets_are_in_sync(self):
        en_path = Path("shared_lib/locales/en.json")
        ru_path = Path("shared_lib/locales/ru.json")

        en_data = json.loads(en_path.read_text(encoding="utf-8"))
        ru_data = json.loads(ru_path.read_text(encoding="utf-8"))

        self.assertEqual(set(en_data.keys()), set(ru_data.keys()))

    def test_translator_fallback_behavior(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            (tmp_path / "en.json").write_text(
                json.dumps({"hello": "Hello", "fallback_only": "Default value"}),
                encoding="utf-8",
            )
            (tmp_path / "ru.json").write_text(
                json.dumps({"hello": "Привет"}),
                encoding="utf-8",
            )

            translator = Translator(locales_dir=tmp_path, default_lang="en")

            self.assertEqual(translator.gettext("ru", "hello"), "Привет")
            self.assertEqual(translator.gettext("ru", "fallback_only"), "Default value")
            self.assertEqual(translator.gettext("es", "fallback_only"), "Default value")
            self.assertEqual(translator.gettext("ru", "missing_key"), "_missing_key_")

    def test_frontend_locale_key_sets_and_placeholders_are_in_sync(self):
        locales_dir = Path("main_site_frontend/locales")
        en_data = json.loads((locales_dir / "en.json").read_text(encoding="utf-8"))
        ru_data = json.loads((locales_dir / "ru.json").read_text(encoding="utf-8"))

        self.assertEqual(set(en_data), set(ru_data))
        placeholder_pattern = re.compile(r"\{(\w+)\}")
        mismatched_placeholders = {
            key: (
                set(placeholder_pattern.findall(en_data[key])),
                set(placeholder_pattern.findall(ru_data[key])),
            )
            for key in en_data
            if set(placeholder_pattern.findall(en_data[key]))
            != set(placeholder_pattern.findall(ru_data[key]))
        }
        self.assertEqual(mismatched_placeholders, {})

    def test_frontend_translation_attributes_reference_known_keys(self):
        locales_dir = Path("main_site_frontend/locales")
        known_keys = set(json.loads((locales_dir / "en.json").read_text(encoding="utf-8")))
        attribute_pattern = re.compile(
            r"data-(?:i18n|i18n-placeholder|i18n-title|i18n-aria-label|"
            r'stats-i18n|stats-placeholder|stats-title|stats-aria-label)="([^"]+)"'
        )
        used_keys: set[str] = set()
        for html_path in Path("main_site_frontend").glob("*.html"):
            used_keys.update(attribute_pattern.findall(html_path.read_text(encoding="utf-8")))

        self.assertEqual(used_keys - known_keys, set())

    def test_frontend_scripts_use_shared_locale_loader(self):
        navbar_source = Path("main_site_frontend/js/navbar.js").read_text(encoding="utf-8")
        stats_source = Path("main_site_frontend/js/stats.js").read_text(encoding="utf-8")
        self.assertNotIn("const I18N =", navbar_source)
        self.assertNotIn("const STATS_I18N =", stats_source)

        for page_name in (
            "index.html",
            "login.html",
            "register.html",
            "schedule.html",
            "stats.html",
            "studio.html",
        ):
            source = Path("main_site_frontend", page_name).read_text(encoding="utf-8")
            loader_position = source.index("/js/frontend_i18n.js")
            navbar_position = source.index("/js/navbar.js")
            self.assertLess(loader_position, navbar_position, page_name)

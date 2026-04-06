import json
import tempfile
import unittest
from pathlib import Path

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

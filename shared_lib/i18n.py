import json
from pathlib import Path
import logging

from .database import get_user_settings

logger = logging.getLogger(__name__)


class Translator:
    def __init__(self, locales_dir: Path, default_lang: str = "en"):
        self.locales_dir = locales_dir
        self.default_lang = default_lang
        self.translations = {}
        self._load_translations()

    def _load_translations(self):
        """Loads all .json language files from the locales directory."""
        for lang_file in self.locales_dir.glob("*.json"):
            lang_code = lang_file.stem
            try:
                with open(lang_file, 'r', encoding='utf-8') as f:
                    self.translations[lang_code] = json.load(f)
                logger.info(f"Successfully loaded language: {lang_code}")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load language file {lang_file}: {e}")

    async def get_user_language(self, user_id: int) -> str:
        """Fetches the user's language from settings, falling back to default."""
        settings = await get_user_settings(user_id)
        return settings.get('language', self.default_lang)

    def gettext(self, lang: str, key: str, **kwargs) -> str:
        """
        Gets a translated string for a given key and language.
        Falls back to the default language if the key is not found.
        """
        text = self.translations.get(lang, {}).get(key)
        if text is None:
            # Fallback to default language
            text = self.translations.get(self.default_lang, {}).get(key, f"_{key}_")

        return text.format(**kwargs)


# Create a single instance of the translator
translator = Translator(locales_dir=Path(__file__).parent / "locales")
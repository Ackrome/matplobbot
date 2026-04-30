import importlib
import sys
import types
import unittest


def _install_matplobblib_stub() -> None:
    if "matplobblib" in sys.modules:
        return

    stub = types.ModuleType("matplobblib")
    stub.submodules = []
    stub._importlib = importlib
    sys.modules["matplobblib"] = stub


_install_matplobblib_stub()

try:
    from bot import keyboards as kb

    KEYBOARDS_AVAILABLE = True
except ModuleNotFoundError as exc:
    if exc.name not in {"aiogram", "cachetools"}:
        raise
    KEYBOARDS_AVAILABLE = False


class _FakeTranslator:
    async def get_language(self, user_id, chat_id=None):
        return "en"

    def gettext(self, lang, key, **kwargs):
        translations = {
            "webapp_open_schedule": "Open Schedule",
            "webapp_open_calendar_sync": "Calendar Sync",
            "webapp_open_studio": "Open Studio",
            "main_menu_placeholder": "Choose a command",
        }
        return translations.get(key, key)


@unittest.skipUnless(KEYBOARDS_AVAILABLE, "bot keyboard dependencies are not installed")
class TestTelegramWebAppKeyboards(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original_public_site_url = kb.PUBLIC_SITE_URL
        self.original_translator = kb.translator
        self.original_warning_flag = kb._WEB_APP_URL_WARNING_EMITTED
        kb.translator = _FakeTranslator()
        kb._WEB_APP_URL_WARNING_EMITTED = False

    def tearDown(self):
        kb.PUBLIC_SITE_URL = self.original_public_site_url
        kb.translator = self.original_translator
        kb._WEB_APP_URL_WARNING_EMITTED = self.original_warning_flag

    def test_web_app_inline_keyboard_uses_https_public_site_url(self):
        kb.PUBLIC_SITE_URL = "https://example.com"

        markup = kb.get_web_apps_inline_keyboard("en")

        self.assertIsNotNone(markup)
        urls = [button.web_app.url for row in markup.inline_keyboard for button in row]
        self.assertEqual(
            urls,
            [
                "https://example.com/schedule?tg=1",
                "https://example.com/schedule?tg=1&calendar=1",
                "https://example.com/studio?tg=1",
            ],
        )

    async def test_invalid_public_site_url_omits_reply_web_app_buttons(self):
        kb.PUBLIC_SITE_URL = "http://localhost:8080"

        markup = await kb.get_main_reply_keyboard(user_id=123)

        buttons = [button for row in markup.keyboard for button in row]
        self.assertFalse(any(button.web_app for button in buttons))
        self.assertIn("/search", [button.text for button in buttons])

    async def test_invalid_public_site_url_omits_inline_web_app_buttons(self):
        kb.PUBLIC_SITE_URL = "http://localhost:8080"

        self.assertIsNone(kb.get_web_apps_inline_keyboard("en"))

        help_markup = await kb.get_help_inline_keyboard(user_id=123)
        buttons = [button for row in help_markup.inline_keyboard for button in row]
        self.assertFalse(any(button.web_app for button in buttons))
        self.assertIn("help_btn_matp_all", [button.text for button in buttons])

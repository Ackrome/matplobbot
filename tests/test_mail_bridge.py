"""Offline mailbox protocol, privacy, MIME and delivery regression tests."""

import asyncio
import importlib.util
import os
import unittest
from email.message import EmailMessage
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from cryptography.fernet import Fernet

from shared_lib.mail_bridge import (
    parse_mail,
    poll_mail,
    seal,
    sensitive_mail_update,
    unseal,
    validate_host,
)


def handlers():
    spec = importlib.util.spec_from_file_location(
        "mail_handlers_test", Path(__file__).parents[1] / "bot/handlers/mail.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MailTests(unittest.TestCase):
    def test_encryption(self):
        with patch.dict(os.environ, MAIL_CREDENTIAL_KEY=Fernet.generate_key().decode()):
            encrypted = seal({"password": "never-log-this"})
            self.assertNotIn(b"never-log-this", encrypted)
            self.assertEqual(unseal(encrypted), {"password": "never-log-this"})

    def test_hosts(self):
        self.assertEqual(validate_host("IMAP.YANDEX.RU", "imap"), "imap.yandex.ru")
        for host in ("127.0.0.1", "metadata.google.internal", "imap.gmail.com/path"):
            with self.assertRaises(ValueError):
                validate_host(host, "imap")
        with self.assertRaises(ValueError):
            validate_host("imap.gmail.com", "pop3")

    def test_mime_and_html(self):
        message = EmailMessage()
        message["Subject"] = "<script>subject</script>"
        message.set_content("plain")
        message.add_alternative(
            '<p><b>Bold</b><img src="http://localhost/secret"><script>bad()</script><a href="javascript:alert(1)">link</a></p>',
            subtype="html",
        )
        message.add_attachment(
            b"data", maintype="application", subtype="octet-stream", filename="../../report.txt"
        )
        result = parse_mail(message.as_bytes(), "user@example.org")
        html = "".join(result["chunks"])
        self.assertIn("<b>Bold</b>", html)
        self.assertNotIn("javascript:", html)
        self.assertNotIn("localhost", html)
        self.assertNotIn("bad()", html)
        self.assertNotIn("<script>", html)
        self.assertEqual(result["attachments"][0]["name"], "report.txt")

    def test_pop_baseline_and_new_message(self):
        client = MagicMock()
        client.uidl.return_value = (b"+OK", [b"1 old", b"2 new"], 10)
        client.list.return_value = b"+OK 2 12"
        client.retr.return_value = (b"+OK", [b"Subject: New", b"", b"hello"], 20)
        with patch("shared_lib.mail_bridge.poplib.POP3_SSL", return_value=client):
            state, raw = poll_mail("pop.yandex.ru", "pop3", "u", "p")
            self.assertIsNone(raw)
            self.assertEqual(state["uids"], ["old", "new"])
            client.retr.assert_not_called()
            state, raw = poll_mail("pop.yandex.ru", "pop3", "u", "p", {"uids": ["old"]})
            self.assertIn(b"hello", raw)
            self.assertEqual(state["uids"], ["old", "new"])
            client.dele.assert_not_called()

    def test_imap_baseline_readonly(self):
        client = MagicMock()
        client.select.return_value = ("OK", [b"2"])
        client.response.return_value = ("UIDVALIDITY", [b"10"])
        client.uid.return_value = ("OK", [b"3 7"])
        with patch("shared_lib.mail_bridge.imaplib.IMAP4_SSL", return_value=client):
            state, raw = poll_mail("imap.gmail.com", "imap", "u", "p")
            self.assertEqual(state, {"validity": "10", "uid": 7})
            self.assertIsNone(raw)
            client.select.assert_called_once_with("INBOX", readonly=True)
            with self.assertRaises(ValueError):
                poll_mail("imap.gmail.com", "imap", "u", "p", {"validity": "9", "uid": 7})

    def test_sensitive_inputs_and_router(self):
        module = handlers()
        self.assertEqual(module.MailManager().router.name, "mail")
        event = SimpleNamespace(message=SimpleNamespace(reply_to_message=None), edited_message=None)
        self.assertTrue(sensitive_mail_update(event, {"raw_state": "MailSetup:password"}))
        event.message.reply_to_message = SimpleNamespace(text=module.PASSWORD_PROMPT)
        self.assertTrue(sensitive_mail_update(event, {}))

    def test_failed_upload_retains_bytes(self):
        async def scenario():
            module = handlers()
            bot = SimpleNamespace(send_document=AsyncMock(side_effect=TimeoutError()))
            pending = {
                "chunks": [],
                "attachments": [{"name": "file.txt", "data": "ZGF0YQ=="}],
                "message_id": 1,
            }
            with self.assertRaises(TimeoutError):
                await module.deliver_step(bot, SimpleNamespace(user_id=1), pending)
            self.assertEqual(len(pending["attachments"]), 1)
            bot.send_document.side_effect = None
            self.assertFalse(await module.deliver_step(bot, SimpleNamespace(user_id=1), pending))
            self.assertEqual(pending["attachments"], [])

        asyncio.run(scenario())

    def test_delivered_text_is_not_resent_for_attachment(self):
        async def scenario():
            module = handlers()
            bot = SimpleNamespace(
                send_rich_message=AsyncMock(return_value=SimpleNamespace(message_id=123)),
                send_document=AsyncMock(),
            )
            pending = {
                "chunks": ["<p>Mail</p>"],
                "attachments": [{"name": "file.txt", "data": "ZGF0YQ=="}],
                "message_id": None,
            }
            self.assertTrue(await module.deliver_step(bot, SimpleNamespace(user_id=1), pending))
            self.assertEqual(pending["message_id"], 123)
            self.assertFalse(await module.deliver_step(bot, SimpleNamespace(user_id=1), pending))
            bot.send_rich_message.assert_awaited_once()
            self.assertEqual(bot.send_document.call_args.kwargs["reply_parameters"].message_id, 123)

        asyncio.run(scenario())

    def test_nested_attached_email(self):
        message = EmailMessage()
        message.set_content("Outer")
        nested = EmailMessage()
        nested.set_content("Inner")
        message.add_attachment(nested, filename="forwarded.eml")
        files = parse_mail(message.as_bytes(), "u@example.com")["attachments"]
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["name"], "forwarded.eml")


if __name__ == "__main__":
    unittest.main()

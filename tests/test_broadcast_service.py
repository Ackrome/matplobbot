import tempfile
import unittest
from pathlib import Path

from shared_lib.services.broadcast_service import (
    MAX_TELEGRAM_MESSAGES_PER_SECOND,
    broadcast_chunks_to_users,
    dedupe_user_ids,
    load_broadcast_text,
    normalize_broadcast_rate,
    resolve_default_broadcast_files,
    split_telegram_message,
)


class TestBroadcastService(unittest.IsolatedAsyncioTestCase):
    def test_normalize_broadcast_rate_caps_telegram_limit(self):
        self.assertEqual(normalize_broadcast_rate(100), MAX_TELEGRAM_MESSAGES_PER_SECOND)
        self.assertEqual(normalize_broadcast_rate(0), 25.0)
        self.assertEqual(normalize_broadcast_rate("bad"), 25.0)

    def test_resolve_default_files_prefers_announcement_and_current_changelog(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            docs = root / "docs"
            docs.mkdir()
            (docs / "announcement.md").write_text("# Announcement", encoding="utf-8")
            (docs / "changelog-from-0.7.1.md").write_text("# Current", encoding="utf-8")
            (docs / "CHANGELOG.md").write_text("# Legacy", encoding="utf-8")

            files = resolve_default_broadcast_files(root)

        self.assertEqual(
            [path.name for path in files],
            ["announcement.md", "changelog-from-0.7.1.md"],
        )

    def test_load_broadcast_text_converts_markdown_to_plain_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "announcement.md"
            source.write_text(
                "# Release\n\n![shot](image.png)\n\nSee [docs](https://example.com).",
                encoding="utf-8",
            )

            text, files = load_broadcast_text([source], root=root, title="Update")

        self.assertEqual(files, [source])
        self.assertIn("Update", text)
        self.assertIn("Release", text)
        self.assertIn("docs (https://example.com)", text)
        self.assertNotIn("![shot]", text)

    def test_split_telegram_message_keeps_chunks_under_limit(self):
        text = "\n\n".join([f"Paragraph {index} " + ("x" * 100) for index in range(80)])
        chunks = split_telegram_message(text, max_chars=1000)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 1000 for chunk in chunks))
        self.assertTrue(chunks[0].startswith("[1/"))

    async def test_broadcast_dry_run_does_not_call_sender(self):
        calls = []

        async def send_message(user_id: int, text: str):
            calls.append((user_id, text))

        result = await broadcast_chunks_to_users(
            [1, 2],
            ["hello"],
            send_message,
            dry_run=True,
        )

        self.assertEqual(calls, [])
        self.assertEqual(result.target_users, 2)
        self.assertEqual(result.total_messages, 2)
        self.assertEqual(result.sent_messages, 0)

    async def test_broadcast_stops_remaining_chunks_after_user_failure(self):
        calls = []

        async def send_message(user_id: int, text: str):
            calls.append((user_id, text))
            if user_id == 1:
                raise RuntimeError("blocked")

        result = await broadcast_chunks_to_users(
            [1, 1, 2],
            ["part 1", "part 2"],
            send_message,
            rate_per_second=1000,
            dry_run=False,
        )

        self.assertEqual(dedupe_user_ids([1, 1, 2]), [1, 2])
        self.assertEqual(calls, [(1, "part 1"), (2, "part 1"), (2, "part 2")])
        self.assertEqual(result.target_users, 2)
        self.assertEqual(result.total_messages, 4)
        self.assertEqual(result.sent_messages, 2)
        self.assertEqual(result.failed_messages, 1)
        self.assertEqual(result.skipped_messages, 1)
        self.assertEqual(result.failed_users, 1)


if __name__ == "__main__":
    unittest.main()

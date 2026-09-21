import unittest

from shared_lib.html_tools import split_telegram_html_message


class TestSchedulerHTMLSplitter(unittest.TestCase):
    def test_short_message_not_split(self):
        msg = "<b>Hello World!</b> Simple schedule update."
        chunks = split_telegram_html_message(msg, max_chars=100)
        self.assertEqual(chunks, [msg])

    def test_empty_message(self):
        self.assertEqual(split_telegram_html_message(""), [])
        self.assertEqual(split_telegram_html_message("   "), [])

    def test_rejects_limit_too_small_for_nested_tags(self):
        msg = '<b><a href="https://example.com">text</a></b>'
        with self.assertRaises(ValueError):
            split_telegram_html_message(msg, max_chars=20)

    def test_split_long_bold_text_preserves_closed_tags(self):
        inner = "Line of text that is fairly long and repeats.\n" * 20
        msg = f"<b>{inner}</b>"
        chunks = split_telegram_html_message(msg, max_chars=200)

        self.assertGreater(len(chunks), 1)
        for i, chunk in enumerate(chunks):
            self.assertTrue(len(chunk) <= 250, f"Chunk {i} too large: {len(chunk)}")
            self.assertTrue(chunk.startswith("<b>"), f"Chunk {i} should start with <b>")
            self.assertTrue(chunk.endswith("</b>"), f"Chunk {i} should end with </b>")

    def test_split_nested_tags(self):
        inner = "Click here to see schedule details.\n" * 15
        msg = f"<b>Notice: <a href=\"https://example.com/sched\">{inner}</a></b>"
        chunks = split_telegram_html_message(msg, max_chars=200)

        self.assertGreater(len(chunks), 1)
        for i, chunk in enumerate(chunks):
            # Verify tag balance in every chunk
            self.assertEqual(chunk.count("<b>"), chunk.count("</b>"), f"Chunk {i} unbalanced <b>")
            self.assertEqual(chunk.count("<a "), chunk.count("</a>"), f"Chunk {i} unbalanced <a>")

    def test_split_preserves_code_and_pre(self):
        inner = "const x = 123;\nconsole.log(x);\n" * 15
        msg = f"<pre><code class=\"language-js\">{inner}</code></pre>"
        chunks = split_telegram_html_message(msg, max_chars=200)

        self.assertGreater(len(chunks), 1)
        for i, chunk in enumerate(chunks):
            self.assertEqual(chunk.count("<pre>"), chunk.count("</pre>"), f"Chunk {i} unbalanced <pre>")
            self.assertEqual(chunk.count("<code"), chunk.count("</code>"), f"Chunk {i} unbalanced <code>")


if __name__ == "__main__":
    unittest.main()

"""Surya adapter contracts without model downloads or Torch imports."""

import io
import json
import unittest
from unittest.mock import Mock

from PIL import Image

from scripts.curriculum_ocr_surya import Surya2Client, html_text


class SuryaAdapterTests(unittest.TestCase):
    def response(self, finish, html):
        body = {"choices": [{"finish_reason": finish, "message": {"content": html}}]}
        client = Surya2Client("http://127.0.0.1:18976/v1")
        client.opener = Mock()
        client.opener.open.return_value = io.BytesIO(json.dumps(body).encode())
        return client, client.recognize(Image.new("RGB", (20, 20), "white"))

    def test_html_cell_separators_are_preserved(self):
        self.assertEqual(html_text("<table><tr><td>1,2</td><td>3</td></tr></table>"), "1,2 3")
        self.assertEqual(html_text("<p>А &amp; Б<br>В</p>"), "А & Б В")

    def test_truncated_response_is_not_a_recognized_value(self):
        _, result = self.response("length", "<p>1,2")
        self.assertTrue(result["abstained"])
        self.assertEqual(result["text"], "")
        self.assertEqual(result["raw_html"], "<p>1,2")

    def test_success_preserves_text_and_exact_publisher_prompt(self):
        client, result = self.response("stop", "<p>Б.1.1.1.5</p>")
        self.assertFalse(result["abstained"])
        self.assertEqual(result["text"], "Б.1.1.1.5")
        request = client.opener.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(
            payload["messages"][0]["content"][1]["text"], "OCR this block image to HTML."
        )
        self.assertEqual(payload["temperature"], 0)
        self.assertNotIn("exam", request.data.decode())

    def test_unbounded_request_settings_are_rejected(self):
        with self.assertRaises(ValueError):
            Surya2Client("http://localhost/v1", timeout=601)
        with self.assertRaises(ValueError):
            Surya2Client("http://localhost/v1", max_tokens=100000)

    def test_explicit_publisher_prompt_and_backend_alias_override(self):
        client = Surya2Client("http://localhost/v1", model_label="paddle", prompt="OCR:")
        client.opener = Mock()
        client.opener.open.return_value = io.BytesIO(
            json.dumps(
                {"choices": [{"finish_reason": "stop", "message": {"content": "1,2,3"}}]}
            ).encode()
        )
        self.assertEqual(client.recognize(Image.new("RGB", (20, 20)))["text"], "1,2,3")
        body = json.loads(client.opener.open.call_args.args[0].data)
        self.assertEqual(body["model"], "paddle")
        self.assertEqual(body["messages"][0]["content"][1]["text"], "OCR:")


if __name__ == "__main__":
    unittest.main()

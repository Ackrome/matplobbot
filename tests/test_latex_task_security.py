import base64
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.services.document_renderer import convert_html_to_telegram_html
from shared_lib.tasks import (
    _validate_latex_source,
    compile_project_task,
    resolve_worker_resource_paths,
    validate_worker_resources,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TestLatexTaskSecurity(unittest.TestCase):
    def test_safe_latex_passes(self):
        safe_code = r"""
        \documentclass{article}
        \begin{document}
        Hello world! $E = mc^2$
        \end{document}
        """
        is_safe, reason = _validate_latex_source(safe_code)
        self.assertTrue(is_safe)
        self.assertIsNone(reason)

    def test_write18_blocked(self):
        evil_code = r"\immediate\write18{id}"
        is_safe, reason = _validate_latex_source(evil_code)
        self.assertFalse(is_safe)
        self.assertIn("write18", reason)

    def test_openin_blocked(self):
        evil_code = r"\newread\myread\openin\myread=/etc/passwd"
        is_safe, reason = _validate_latex_source(evil_code)
        self.assertFalse(is_safe)
        self.assertTrue("openin" in reason or "newread" in reason)

    def test_path_traversal_input_blocked(self):
        evil_code = r"\input{../secret.txt}"
        is_safe, reason = _validate_latex_source(evil_code)
        self.assertFalse(is_safe)
        self.assertIn("input", reason)

    def test_absolute_path_input_blocked(self):
        evil_code = r"\input{/etc/passwd}"
        is_safe, reason = _validate_latex_source(evil_code)
        self.assertFalse(is_safe)
        self.assertIn("input", reason)

    def test_file_write_commands_blocked(self):
        for evil_code in (r"\openout\file=/tmp/pwn", r"\newwrite\file"):
            is_safe, reason = _validate_latex_source(evil_code)
            self.assertFalse(is_safe)
            self.assertIn("I/O", reason)

    def test_nested_path_traversal_blocked(self):
        evil_code = r"\input{chapters/../../secret.txt}"
        is_safe, reason = _validate_latex_source(evil_code)
        self.assertFalse(is_safe)
        self.assertIn("traversal", reason)

    def test_comment_obfuscation_is_blocked(self):
        evil_code = "\\input% hide the command boundary\n{/etc/passwd}"
        is_safe, reason = _validate_latex_source(evil_code)
        self.assertFalse(is_safe)
        self.assertIn("input", reason)

    def test_binary_latex_is_validated_before_compilation(self):
        binary_tex = base64.b64encode(rb"\input{/etc/passwd}").decode()
        project_files = [{"path": "main.tex", "binary": binary_tex}]
        with patch("subprocess.run") as mock_run:
            result = compile_project_task.run(project_files, "main.tex")
        self.assertEqual(result["status"], "error")
        self.assertIn("Security restriction", result["message"])
        mock_run.assert_not_called()

    def test_worker_resources_resolve_in_checkout_and_container_layout(self):
        checkout_paths = resolve_worker_resource_paths({}, project_root=PROJECT_ROOT)
        self.assertTrue(all(path.is_file() for path in checkout_paths.values()))
        validate_worker_resources()

        container_paths = resolve_worker_resource_paths(
            {
                "APP_BOT_DIR": "/app/bot",
                "APP_TEMPLATES_DIR": "/app/bot/templates",
            },
            project_root=Path("/unused"),
        )
        self.assertTrue(
            container_paths["mermaid_filter"]
            .as_posix()
            .endswith("/app/bot/pandoc_mermaid_filter.py")
        )
        self.assertTrue(
            container_paths["pandoc_header"]
            .as_posix()
            .endswith("/app/bot/templates/pandoc_header.tex")
        )

        worker_dockerfile = (PROJECT_ROOT / "Dockerfile.worker").read_text(encoding="utf-8")
        self.assertIn("APP_BOT_DIR=/app/bot", worker_dockerfile)
        self.assertIn("APP_TEMPLATES_DIR=/app/bot/templates", worker_dockerfile)
        for resource in (
            "bot/puppeteer-config.json",
            "bot/pandoc_mermaid_filter.py",
            "bot/pandoc_math_filter.lua",
            "bot/templates/",
        ):
            self.assertIn(resource, worker_dockerfile)

    def test_html_converter_allows_only_telegram_markup(self):
        source = """
            <h2 class="title">Heading <em data-extra="x">italic</em></h2>
            <ol><li>First<ul><li>Nested</li></ul></li></ol>
            <table><tr><th scope="col">Name</th><td>Value</td></tr></table>
            <a href="javascript:alert(1)" onclick="bad()">unsafe</a>
            <a href="https://example.com/?a=1&amp;b=2" onclick="bad()">safe link</a>
            <custom-tag data-x="1">kept &amp; escaped &lt;text&gt;</custom-tag>
        """

        converted = convert_html_to_telegram_html(source)

        self.assertIn("<b>Heading <i>italic</i></b>", converted)
        self.assertIn("1. First", converted)
        self.assertIn("• Nested", converted)
        self.assertIn("<b>Name</b> | Value |", converted)
        self.assertIn('<a href="https://example.com/?a=1&amp;b=2">safe link</a>', converted)
        self.assertIn("kept &amp; escaped &lt;text&gt;", converted)
        self.assertNotIn("javascript:", converted)
        self.assertNotIn("onclick", converted)
        self.assertNotIn("custom-tag", converted)
        self.assertNotIn('class="title"', converted)

    def test_html_converter_sanitizes_unknown_and_nested_attributes(self):
        converted = convert_html_to_telegram_html(
            '<pre data-x="1"><code class="language-python" onclick="bad()">'
            'print("&lt;ok&gt;")</code></pre><script>alert(1)</script>'
        )

        self.assertIn('<pre><code class="language-python">', converted)
        self.assertIn('print("&lt;ok&gt;")', converted)
        self.assertIn("alert(1)", converted)
        self.assertNotIn("<script", converted)
        self.assertNotIn("onclick", converted)

    @patch("subprocess.run")
    def test_compile_project_task_rejects_evil_file_before_compilation(self, mock_run):
        project_files = [
            {
                "path": "main.tex",
                "text": r"\documentclass{article}\begin{document}\write18{rm -rf /}\end{document}",
            }
        ]
        result = compile_project_task.run(project_files, "main.tex")
        self.assertEqual(result["status"], "error")
        self.assertIn("Security restriction", result["message"])
        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()

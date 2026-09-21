import base64
import unittest
from unittest.mock import patch

from shared_lib.tasks import _validate_latex_source, compile_project_task


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
        binary_tex = base64.b64encode(br"\input{/etc/passwd}").decode()
        project_files = [{"path": "main.tex", "binary": binary_tex}]
        with patch("subprocess.run") as mock_run:
            result = compile_project_task.run(project_files, "main.tex")
        self.assertEqual(result["status"], "error")
        self.assertIn("Security restriction", result["message"])
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_compile_project_task_rejects_evil_file_before_compilation(self, mock_run):
        project_files = [
            {"path": "main.tex", "text": r"\documentclass{article}\begin{document}\write18{rm -rf /}\end{document}"}
        ]
        result = compile_project_task.run(project_files, "main.tex")
        self.assertEqual(result["status"], "error")
        self.assertIn("Security restriction", result["message"])
        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()

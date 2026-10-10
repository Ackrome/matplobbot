"""Real Linux isolation probes; CI/container opts in and fails if unavailable."""

import base64
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared_lib.render_assets import allowed_project_path
from shared_lib.render_sandbox import RenderSandboxUnavailable, run_render_process, sandbox_command


class TestRenderPolicy(unittest.TestCase):
    def test_config_and_traversal_files_rejected(self):
        for name in (
            ".latexmkrc",
            "latexmkrc",
            "texmf.cnf",
            "../main.tex",
            ".hidden/main.tex",
            "image.svg",
            "page.html",
            "main.lua",
            "/main.tex",
            "a/../main.tex",
        ):
            self.assertFalse(allowed_project_path(name), name)
        for name in ("main.tex", "chapters/one.tex", "references.bib", "картинка.png"):
            self.assertTrue(allowed_project_path(name), name)

    def test_no_unsandboxed_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("shared_lib.render_sandbox.shutil.which", return_value=None):
                with self.assertRaises(RenderSandboxUnavailable):
                    sandbox_command(["latexmk", "main.tex"], workdir=directory)

    def test_root_worker_is_rejected(self):
        with patch("shared_lib.render_sandbox.sys.platform", "linux"):
            with patch("shared_lib.render_sandbox.os.geteuid", return_value=0, create=True):
                with self.assertRaisesRegex(RenderSandboxUnavailable, "non-root"):
                    sandbox_command(["latexmk", "main.tex"], workdir="/")


@unittest.skipUnless(
    os.getenv("RENDER_SANDBOX_INTEGRATION") == "1", "run explicitly in the built Linux worker image"
)
class TestRenderSandboxIntegration(unittest.TestCase):
    def run_process(self, command, directory, **kwargs):
        return run_render_process(
            command,
            workdir=directory,
            capture_output=True,
            text=True,
            timeout=kwargs.pop("timeout", 20),
            **kwargs,
        )

    def test_files_env_processes_network_and_readonly_runtime(self):
        with tempfile.TemporaryDirectory() as outside, tempfile.TemporaryDirectory() as directory:
            marker = Path(outside) / "outside-canary.txt"
            marker.write_text("SYNTHETIC_SECRET", encoding="utf-8")
            code = """import json,os,pathlib,socket
p=pathlib.Path(MARKER_PATH)
s=socket.socket();s.settimeout(.2)
try:s.connect(("1.1.1.1",80));network=True
except OSError:network=False
try:pathlib.Path("/usr/sandbox-write-canary").write_text("bad");writable=True
except OSError:writable=False
print(json.dumps({"outside":p.exists(),"env":os.getenv("AUDIT_SECRET_CANARY"),
"network":network,"runtime_writable":writable,"parent_process":os.readlink("/proc/self/ns/pid")==PARENT_NAMESPACE}))
""".replace("MARKER_PATH", repr(str(marker))).replace(
                "PARENT_NAMESPACE", repr(os.readlink("/proc/self/ns/pid"))
            )
            with patch.dict(os.environ, {"AUDIT_SECRET_CANARY": "SYNTHETIC_SECRET"}):
                result = self.run_process(["python3", "-c", code], directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(result.stdout),
                {
                    "outside": False,
                    "env": None,
                    "network": False,
                    "runtime_writable": False,
                    "parent_process": False,
                },
            )

    def test_latex_success_and_local_rc_never_executes(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, ".latexmkrc").write_text(
                'open(my $f, ">", "rc-executed"); print $f "bad"; close($f);', encoding="utf-8"
            )
            Path(directory, "main.tex").write_text(
                r"\documentclass{article}\begin{document}Sandbox $E=mc^2$\end{document}",
                encoding="utf-8",
            )
            result = self.run_process(
                [
                    "latexmk",
                    "-norc",
                    "-pdf",
                    "-no-shell-escape",
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "main.tex",
                ],
                directory,
                timeout=50,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(Path(directory, "main.pdf").read_bytes().startswith(b"%PDF"))
            self.assertFalse(Path(directory, "rc-executed").exists())

    def test_macro_file_read_cannot_escape_workdir(self):
        with tempfile.TemporaryDirectory() as outside, tempfile.TemporaryDirectory() as directory:
            marker = Path(outside, "outside.tex")
            marker.write_text("SYNTHETICSECRET", encoding="utf-8")
            Path(directory, "main.tex").write_text(
                r"\documentclass{article}\begin{document}\csname input\endcsname{"
                + str(marker)
                + r"}\end{document}",
                encoding="utf-8",
            )
            result = self.run_process(
                [
                    "latexmk",
                    "-norc",
                    "-pdf",
                    "-no-shell-escape",
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "main.tex",
                ],
                directory,
                timeout=50,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("SYNTHETICSECRET", result.stdout + result.stderr)

    def test_timeout_cleans_up_a_background_child(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory, "child-survived")
            code = (
                "import subprocess,time;subprocess.Popen(['python3','-c',"
                + repr(
                    "import time,pathlib;time.sleep(2);pathlib.Path("
                    + repr(str(target))
                    + ").write_text('bad')"
                )
                + "]);time.sleep(20)"
            )
            with self.assertRaises(subprocess.TimeoutExpired):
                self.run_process(["python3", "-c", code], directory, timeout=0.2)
            # A fresh sandbox command provides the wait; no host child remains to write.
            self.run_process(["python3", "-c", "import time;time.sleep(2.2)"], directory)
            self.assertFalse(target.exists())

    def test_output_symlink_is_rejected_before_worker_reads_it(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RenderSandboxUnavailable):
                self.run_process(
                    ["python3", "-c", "import os;os.symlink('/etc/passwd','main.pdf')"],
                    directory,
                )

    def test_successful_exit_reaps_detached_background_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory, "child-survived")
            ready = Path(directory, "child-ready")
            child = (
                "import os,pathlib,time;os.setsid();pathlib.Path("
                + repr(str(ready))
                + ").write_text('ready');time.sleep(1);os.symlink('/etc/passwd',"
                + repr(str(target))
                + ")"
            )
            parent = (
                "import subprocess,pathlib,time;subprocess.Popen(['python3','-c',"
                + repr(child)
                + "]);\nwhile not pathlib.Path("
                + repr(str(ready))
                + ").exists():time.sleep(.01)\n"
            )
            result = self.run_process(["python3", "-c", parent], directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(ready.exists(), "The detached child actually started")
            # No writer may survive between the completed process and host file reads.
            result = self.run_process(["python3", "-c", "import time;time.sleep(1.2)"], directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(os.path.lexists(target))

    def test_every_render_task_produces_a_real_artifact(self):
        from shared_lib.tasks import (
            compile_full_latex_task,
            compile_project_task,
            render_latex,
            render_mermaid,
            render_pdf_task,
        )

        source = r"\documentclass{article}\begin{document}Safe $E=mc^2$\end{document}"
        cases = [
            ("latex", compile_full_latex_task, (source,)),
            ("project", compile_project_task, ([{"path": "main.tex", "text": source}], "main.tex")),
            ("formula", render_latex, ("E=mc^2", 5, 150, True)),
            (
                "markdown",
                render_pdf_task,
                ("# Safe document\n\n$E=mc^2$\n", "Test", "Test", "Today"),
            ),
            ("mermaid", render_mermaid, ("graph TD; A[Start] --> B[Done]",)),
            (
                "markdown-mermaid",
                render_pdf_task,
                (
                    "# Diagram\n\n```mermaid\ngraph TD; A[Start] --> B[Done]\n```\n",
                    "Test",
                    "Test",
                    "Today",
                ),
            ),
        ]
        for name, task, args in cases:
            with self.subTest(renderer=name):
                result = task.run(*args)
                self.assertEqual(result.get("status"), "success", result)
                self.assertTrue(result.get("pdf") or result.get("image"), result)
                if name == "markdown-mermaid":
                    import pdfplumber

                    with pdfplumber.open(io.BytesIO(base64.b64decode(result["pdf"]))) as pdf:
                        self.assertTrue(any(page.images for page in pdf.pages))


if __name__ == "__main__":
    unittest.main()

import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from shared_lib.studio_process import StudioBuildCancelled, run_studio_process


class TestStudioProcess(unittest.TestCase):
    def test_cancel_before_start_does_not_launch_a_compiler(self):
        client = Mock()
        client.exists.return_value = True
        with (
            patch("shared_lib.studio_process.Redis.from_url", return_value=client),
            patch("shared_lib.studio_process.subprocess.Popen") as launch,
        ):
            with self.assertRaises(StudioBuildCancelled):
                run_studio_process([sys.executable, "-c", "pass"], studio_job_id="job")
        launch.assert_not_called()
        client.close.assert_called_once()

    def test_cancel_running_process_returns_promptly(self):
        client = Mock()
        client.exists.side_effect = [False, False, True]
        start = time.monotonic()
        with patch("shared_lib.studio_process.Redis.from_url", return_value=client):
            with self.assertRaises(StudioBuildCancelled):
                run_studio_process(
                    [sys.executable, "-c", "import time;time.sleep(30)"],
                    studio_job_id="job",
                    capture_output=True,
                    timeout=10,
                )
        self.assertLess(time.monotonic() - start, 5)
        client.close.assert_called_once()

    def test_stdin_stdout_and_nonzero_exit_survive_polling(self):
        client = Mock()
        client.exists.return_value = False
        with patch("shared_lib.studio_process.Redis.from_url", return_value=client):
            result = run_studio_process(
                [
                    sys.executable,
                    "-c",
                    "import sys,time;data=sys.stdin.buffer.read();time.sleep(.7);sys.stdout.buffer.write(data);sys.exit(3)",
                ],
                studio_job_id="job",
                input="Текст".encode(),
                capture_output=True,
                timeout=5,
            )
        self.assertEqual(result.stdout, "Текст".encode())
        self.assertEqual(result.returncode, 3)

    def test_timeout_stops_the_compiler(self):
        client = Mock()
        client.exists.return_value = False
        with patch("shared_lib.studio_process.Redis.from_url", return_value=client):
            with self.assertRaises(subprocess.TimeoutExpired):
                run_studio_process(
                    [sys.executable, "-c", "import time;time.sleep(30)"],
                    studio_job_id="job",
                    capture_output=True,
                    timeout=0.1,
                )

    def test_non_studio_call_keeps_existing_transport(self):
        with patch("shared_lib.studio_process.subprocess.run", return_value="result") as run:
            self.assertEqual(run_studio_process(["compiler"], timeout=2), "result")
        run.assert_called_once_with(["compiler"], timeout=2)


class TestCompilerErrorLocations(unittest.TestCase):
    def test_included_file_and_legacy_line_are_preserved(self):
        from shared_lib.tasks import parse_latex_log

        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "main.log"
            log.write_text(
                "./chapters/part.tex:27: Undefined control sequence.\n! Missing $ inserted.\nl.31 Formula\n",
                encoding="utf-8",
            )
            self.assertEqual(
                parse_latex_log(str(log)),
                [
                    {
                        "file": "chapters/part.tex",
                        "line": 27,
                        "message": "Undefined control sequence.",
                    },
                    {"line": 31, "message": "Missing $ inserted."},
                ],
            )

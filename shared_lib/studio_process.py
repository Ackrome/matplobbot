"""Cancel only the compiler process group belonging to one Studio job."""

import os
import signal
import subprocess
import tempfile
import time

from redis import Redis

from .redis_client import get_redis_url

CANCEL_PREFIX = "mpb:studio-cancel:"
MAX_CAPTURE_BYTES = 2 * 1024 * 1024


class StudioBuildCancelled(Exception):
    """The owner requested cancellation of this exact build."""


def run_studio_process(command, *, studio_job_id=None, **kwargs):
    """Like subprocess.run, with bounded polling and cleanup for Studio jobs.

    All calls, including Telegram renders, get process-tree cleanup on timeout.
    In production (POSIX), the sandbox and its descendants get a private process
    group. Cancellation never signals a reusable Celery worker process.
    """
    timeout = kwargs.pop("timeout", 50)
    input_data = kwargs.pop("input", None)
    capture_files = []
    if kwargs.pop("capture_output", False):
        # Compiler diagnostics are untrusted too. Files avoid unbounded Python
        # communicate buffers; sandbox RLIMIT_FSIZE and worker tmpfs bound writes.
        capture_files = [tempfile.TemporaryFile(), tempfile.TemporaryFile()]
        kwargs.update(stdout=capture_files[0], stderr=capture_files[1])
    if input_data is not None:
        kwargs["stdin"] = subprocess.PIPE
    kwargs["start_new_session"] = os.name == "posix"
    client = None
    process = None
    completed = False
    deadline = time.monotonic() + timeout
    try:
        if studio_job_id:
            client = Redis.from_url(get_redis_url(), socket_timeout=1, socket_connect_timeout=1)
        if client and client.exists(CANCEL_PREFIX + studio_job_id):
            raise StudioBuildCancelled()
        process = subprocess.Popen(command, **kwargs)
        while True:
            if client and client.exists(CANCEL_PREFIX + studio_job_id):
                raise StudioBuildCancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                stdout, stderr = process.communicate(input=input_data, timeout=min(0.5, remaining))
                completed = True
                if capture_files:
                    captured = []
                    for stream in capture_files:
                        stream.seek(0)
                        value = stream.read(MAX_CAPTURE_BYTES)
                        if (
                            kwargs.get("text")
                            or kwargs.get("universal_newlines")
                            or kwargs.get("encoding")
                        ):
                            value = value.decode(
                                kwargs.get("encoding") or "utf-8", kwargs.get("errors") or "replace"
                            )
                        captured.append(value)
                    stdout, stderr = captured
                return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                # communicate resumes the same input buffer on subsequent calls.
                input_data = None
    finally:
        if process is not None and not completed:
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif process.poll() is None:
                process.kill()
            process.communicate()
        if client:
            client.close()
        for stream in capture_files:
            stream.close()

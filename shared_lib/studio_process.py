"""Cancel only the compiler process group belonging to one Studio job."""

import os
import signal
import subprocess
import time

from redis import Redis

from .redis_client import get_redis_url

CANCEL_PREFIX = "mpb:studio-cancel:"


class StudioBuildCancelled(Exception):
    """The owner requested cancellation of this exact build."""


def run_studio_process(command, *, studio_job_id=None, **kwargs):
    """Like subprocess.run, with bounded polling and cleanup for Studio jobs.

    Legacy callers retain subprocess.run behavior. In production (POSIX), the
    compiler and its descendants get a private process group. Cancellation never
    sends a signal to a reusable Celery worker process.
    """
    if not studio_job_id:
        return subprocess.run(command, **kwargs)
    timeout = kwargs.pop("timeout", 50)
    input_data = kwargs.pop("input", None)
    if kwargs.pop("capture_output", False):
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if input_data is not None:
        kwargs["stdin"] = subprocess.PIPE
    kwargs["start_new_session"] = os.name == "posix"
    client = Redis.from_url(get_redis_url(), socket_timeout=1, socket_connect_timeout=1)
    process = None
    completed = False
    deadline = time.monotonic() + timeout
    try:
        if client.exists(CANCEL_PREFIX + studio_job_id):
            raise StudioBuildCancelled()
        process = subprocess.Popen(command, **kwargs)
        while True:
            if client.exists(CANCEL_PREFIX + studio_job_id):
                raise StudioBuildCancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                stdout, stderr = process.communicate(input=input_data, timeout=min(0.5, remaining))
                completed = True
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
        client.close()

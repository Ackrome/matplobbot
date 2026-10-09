"""Record successful scheduler work, including partial failures reported by jobs."""

import functools
import time

from shared_lib.operational_metrics import record_operation


def monitor_job(operation, job):
    """Wrap an async scheduled function with bounded, content-free heartbeats."""

    @functools.wraps(job)
    async def monitored(*args, **kwargs):
        started = time.monotonic()
        successful = False
        error_code = "job_exception"
        try:
            result = await job(*args, **kwargs)
            successful = not isinstance(result, dict) or not (
                result.get("failed", 0) or result.get("rescheduled", 0)
            )
            error_code = None if successful else "partial_failure"
            return result
        finally:
            await record_operation(
                operation,
                successful=successful,
                duration_seconds=time.monotonic() - started,
                error_code=error_code,
            )

    return monitored

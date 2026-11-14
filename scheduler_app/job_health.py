"""Record successful scheduler work, including partial failures reported by jobs."""

import asyncio
import functools
import logging
import time

from shared_lib.operational_metrics import record_operation

logger = logging.getLogger(__name__)
SCHEDULE_RETRY_DELAYS_SECONDS = (60, 300, 900)


def _succeeded(result):
    return not isinstance(result, dict) or not (
        result.get("failed", 0) or result.get("rescheduled", 0)
    )


def monitor_job(operation, job):
    """Wrap an async scheduled function with bounded, content-free heartbeats."""

    @functools.wraps(job)
    async def monitored(*args, **kwargs):
        started = time.monotonic()
        successful = False
        error_code = "job_exception"
        try:
            result = await job(*args, **kwargs)
            successful = _succeeded(result)
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


def retry_schedule_job(operation, job, alert, *, delays=SCHEDULE_RETRY_DELAYS_SECONDS):
    """Retry within the scheduled invocation, retaining single-instance execution."""
    monitored = monitor_job(operation, job)

    @functools.wraps(job)
    async def run(*args, **kwargs):
        for attempt in range(len(delays) + 1):
            failure = None
            result = None
            try:
                result = await monitored(*args, **kwargs)
                if _succeeded(result):
                    return result
            except Exception as exc:
                failure = exc
                logger.warning("Schedule job %s failed (%s)", operation, type(exc).__name__)

            if attempt < len(delays):
                await asyncio.sleep(delays[attempt])

        logger.error("Schedule job %s exhausted its retries", operation)
        try:
            await alert(operation)
        except Exception as exc:
            logger.warning("Schedule job alert unavailable (%s)", type(exc).__name__)
        if failure is not None:
            raise failure
        return result

    return run

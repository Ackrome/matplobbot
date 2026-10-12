"""Run the strict dependency gate, retrying only transient network failures."""

from __future__ import annotations

import argparse
import runpy
import sys
import time
import traceback
from pathlib import Path

from requests.exceptions import ConnectionError, HTTPError, SSLError, Timeout

MAX_ATTEMPTS = 3
SOCKET_TIMEOUT_SECONDS = 60
RETRY_DELAYS_SECONDS = (5, 10)
TRANSIENT_HTTP_STATUSES = {429, 500, 502, 503, 504}


def is_transient_network_error(error: BaseException) -> bool:
    """Inspect typed causes, including network errors translated to CLI exits."""
    seen: set[int] = set()
    transient = False
    pending = [error]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        # SSLError inherits ConnectionError; certificate failures must not be retried.
        if isinstance(current, SSLError):
            return False
        if isinstance(current, (Timeout, ConnectionError)):
            transient = True
        if isinstance(current, HTTPError) and current.response is not None:
            transient |= current.response.status_code in TRANSIENT_HTTP_STATUSES
        pending.extend(
            linked for linked in (current.__cause__, current.__context__) if linked is not None
        )
    return transient


def run_audit(requirements: Path) -> int:
    """Invoke the public module entrypoint; preserve all non-network failures."""
    original_argv = sys.argv
    sys.argv = [
        "pip-audit",
        "--strict",
        "--progress-spinner",
        "off",
        "--timeout",
        str(SOCKET_TIMEOUT_SECONDS),
        "-r",
        str(requirements),
        # PYSEC-2024-277 is disputed, with no fixed release as of 2026-05-20.
        # joblib is transitive via matplobblib/scikit-learn; the application
        # does not load untrusted joblib pickle files. No other ignores allowed.
        "--ignore-vuln",
        "PYSEC-2024-277",
    ]
    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            print(f"Dependency security audit: attempt {attempt}/{MAX_ATTEMPTS}", flush=True)
            try:
                # Use the same entrypoint as `python -m pip_audit`, without relying
                # on private scanner APIs or matching advisory/traceback text.
                runpy.run_module("pip_audit", run_name="__main__")
            except (Exception, SystemExit) as error:
                if not is_transient_network_error(error):
                    raise
                if attempt == MAX_ATTEMPTS:
                    traceback.print_exception(error, file=sys.stderr)
                    print(
                        "ERROR: security audit incomplete after transient network failures; "
                        "the dependency gate remains closed.",
                        file=sys.stderr,
                        flush=True,
                    )
                    return 1
                delay = RETRY_DELAYS_SECONDS[attempt - 1]
                print(
                    f"Transient audit network failure; retrying in {delay}s "
                    f"(socket timeout: {SOCKET_TIMEOUT_SECONDS}s).",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(delay)
            else:
                return 0
    finally:
        sys.argv = original_argv
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-r", "--requirement", type=Path, default=Path("audit-requirements.txt"))
    args = parser.parse_args()
    return run_audit(args.requirement)


if __name__ == "__main__":
    raise SystemExit(main())

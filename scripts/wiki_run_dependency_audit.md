# run_dependency_audit.py

## Purpose

Shared strict security-audit entrypoint for GitHub CI, the daily Dependency Audit,
Jenkins and local checks. A slow PyPI response must not cause an immediate flaky
failure, but an incomplete audit must never pass.

## Public functions

- `is_transient_network_error(error)` examines typed exception causes/contexts.
  It recognizes Requests timeouts, connection failures and HTTP 429/500/502/503/504.
  TLS failures are excluded even though Requests makes them connection errors.
- `run_audit(requirements)` invokes the public `pip_audit` module entrypoint with
  strict collection, a 60-second socket timeout and the existing sole joblib
  exception. It makes at most three attempts, separated by 5 and 10 seconds.
  Network exhaustion returns 1; other scanner failures propagate immediately.
- `main()` accepts an optional `-r/--requirement` path, defaulting to
  `audit-requirements.txt`.

## Usage

```sh
python scripts/build_audit_requirements.py
python scripts/run_dependency_audit.py
python scripts/run_dependency_audit.py -r audit-requirements.txt
```

## Dependencies and side effects

Requires the pinned `pip-audit` from `requirements-validation.txt` and its Requests
dependency. Uses `runpy` rather than importing private scanner entrypoints. It
temporarily replaces and restores `sys.argv`, queries the vulnerability service,
resolves dependencies using pip and uses the scanner's normal HTTP cache. Run it
as a dedicated CLI process, not concurrently within an application process.

## Maintenance

Vulnerability findings, strict collection errors, invalid input, TLS failures and
unknown errors are not retried. No stderr/advisory text matching is used.
`SystemExit` is inspected because the scanner can translate a network error into
an exit while preserving its typed exception context. Each retry starts after
leaving the previous exception handler, so an earlier timeout cannot contaminate
the next finding's context.

Socket timeout is not an overall deadline. GitHub audit steps have a 20-minute
timeout; Jenkins uses GNU `timeout --kill-after=10s 20m` for the same boundary.
Local runs do not impose a total deadline. Revalidate real CLI failure injection
in `tests/test_run_dependency_audit.py` whenever upgrading pip-audit. Keep the
documented `PYSEC-2024-277` exception narrow; do not add ignores for transport
failures or skip dependency resolution to shorten an audit.

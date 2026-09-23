# `test_logging_config.py`

## Purpose

Regression tests for environment-driven service logging.

## Coverage

- Accepted and rejected `LOG_LEVEL` values, including aliases.
- `LOG_FORMAT` validation and production/development defaults.
- A subprocess smoke test proving that configured JSON output is valid and contains stable fields plus the active correlation ID.

## Usage

```powershell
.venv\Scripts\python.exe -m unittest tests.test_logging_config
```

## Dependencies and side effects

Uses the standard library, `shared_lib.logging_config`, and a short child Python process. It does not write log files or mutate project state.

## Maintenance notes

Update the field assertions only when the documented structured-log contract intentionally changes. Keep the subprocess isolation so logging handler changes do not interfere with the test runner.

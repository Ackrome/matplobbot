# `logging_config.py`

## Purpose

Provides one stdout/stderr logging policy for the bot, FastAPI API, and scheduler. It validates operator-provided levels, selects human-readable or JSON output, and preserves request correlation IDs.

## Public API

- `configure_logging(service_name, stream=None)` configures the root logger and existing Uvicorn handlers, then returns the resolved `LoggingSettings`.
- `resolve_log_level(value=None)` validates `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`; `WARN` and `FATAL` are accepted aliases.
- `resolve_log_format(value=None, environment=None)` validates `text` or `json`. With no explicit value, production uses JSON and other environments use text.
- `JsonFormatter` emits one JSON object per record with timestamp, level, service, logger, message, correlation ID, and source location.

## Usage

```python
from shared_lib.logging_config import configure_logging

configure_logging("matplobbot-bot")
```

Set `LOG_LEVEL=DEBUG` while diagnosing a service. Set `LOG_FORMAT=json` for machine-readable output or omit it in production, where JSON is the default.

## Dependencies and side effects

The module uses only the standard library and `shared_lib.request_context`. Calling `configure_logging()` replaces the process root handlers and updates existing Uvicorn handlers. Logs remain console-only; Docker performs retention.

## Maintenance notes

Keep the JSON field names stable for log collectors. Do not add file handlers here. When adding a service, give it a stable service name and keep Docker `json-file` size/retention limits in both Compose configurations.

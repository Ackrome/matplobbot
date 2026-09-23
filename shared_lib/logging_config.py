"""Shared stdout logging configuration for Matplobbot services."""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TextIO

from .request_context import CorrelationIdLogFilter, configure_correlation_logging

_LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
_LOG_LEVEL_ALIASES = {"WARN": "WARNING", "FATAL": "CRITICAL"}
_LOG_FORMATS = {"json", "text"}
_PRODUCTION_ENVIRONMENTS = {"prod", "production"}


@dataclass(frozen=True, slots=True)
class LoggingSettings:
    """Resolved logging settings applied to a process."""

    level_name: str
    level: int
    format_name: str


class JsonFormatter(logging.Formatter):
    """Render one structured JSON object per log record."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "service": self.service_name,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", "-"),
            "source": {
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
            },
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def resolve_log_level(value: str | None = None) -> tuple[str, int]:
    """Resolve and validate ``LOG_LEVEL`` (default: ``INFO``)."""

    raw_value = os.getenv("LOG_LEVEL", "INFO") if value is None else value
    level_name = (raw_value or "INFO").strip().upper()
    level_name = _LOG_LEVEL_ALIASES.get(level_name, level_name)
    if level_name not in _LOG_LEVELS:
        allowed = ", ".join(_LOG_LEVELS)
        raise ValueError(f"Invalid LOG_LEVEL {raw_value!r}; expected one of: {allowed}")
    return level_name, _LOG_LEVELS[level_name]


def resolve_log_format(
    value: str | None = None,
    *,
    environment: str | None = None,
) -> str:
    """Resolve ``LOG_FORMAT``; production defaults to JSON, others to text."""

    environment_name = (
        os.getenv("ENVIRONMENT", "development") if environment is None else environment
    )
    default_format = (
        "json" if (environment_name or "").strip().lower() in _PRODUCTION_ENVIRONMENTS else "text"
    )
    raw_value = os.getenv("LOG_FORMAT", "") if value is None else value
    format_name = (raw_value or default_format).strip().lower()
    if format_name not in _LOG_FORMATS:
        allowed = ", ".join(sorted(_LOG_FORMATS))
        raise ValueError(f"Invalid LOG_FORMAT {raw_value!r}; expected one of: {allowed}")
    return format_name


def configure_logging(
    service_name: str,
    *,
    stream: TextIO | None = None,
) -> LoggingSettings:
    """Configure deterministic console logging for one service process."""

    level_name, level = resolve_log_level()
    format_name = resolve_log_format()
    formatter: logging.Formatter
    if format_name == "json":
        formatter = JsonFormatter(service_name)
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - "
            f"[service={service_name}] - [cid=%(correlation_id)s] - "
            "%(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(formatter)
    handler.addFilter(CorrelationIdLogFilter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
    configure_correlation_logging()

    # Uvicorn installs non-propagating handlers before importing the ASGI app.
    # Reformat them as well so API access/error logs follow the selected policy.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        framework_logger = logging.getLogger(logger_name)
        framework_logger.setLevel(level)
        for framework_handler in framework_logger.handlers:
            framework_handler.setFormatter(formatter)
            if not any(
                isinstance(item, CorrelationIdLogFilter) for item in framework_handler.filters
            ):
                framework_handler.addFilter(CorrelationIdLogFilter())

    return LoggingSettings(
        level_name=level_name,
        level=level,
        format_name=format_name,
    )

import contextvars
import logging
import uuid
from contextlib import contextmanager
from typing import Iterator

CORRELATION_ID_HEADER = "X-Request-ID"
_correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id",
    default="-",
)


def generate_correlation_id(prefix: str = "req") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:20]}"


def get_correlation_id() -> str:
    return _correlation_id_var.get()


def set_correlation_id(value: str) -> contextvars.Token[str]:
    return _correlation_id_var.set((value or "-").strip() or "-")


def reset_correlation_id(token: contextvars.Token[str]) -> None:
    _correlation_id_var.reset(token)


@contextmanager
def correlation_scope(prefix: str = "op", correlation_id: str | None = None) -> Iterator[str]:
    value = correlation_id or generate_correlation_id(prefix=prefix)
    token = set_correlation_id(value)
    try:
        yield value
    finally:
        reset_correlation_id(token)


class CorrelationIdLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id()
        return True


def configure_correlation_logging() -> None:
    """Inject correlation id into records emitted by current root handlers."""
    filter_instance = CorrelationIdLogFilter()
    root_logger = logging.getLogger()

    if not any(isinstance(item, CorrelationIdLogFilter) for item in root_logger.filters):
        root_logger.addFilter(filter_instance)

    for handler in root_logger.handlers:
        if not any(isinstance(item, CorrelationIdLogFilter) for item in handler.filters):
            handler.addFilter(filter_instance)

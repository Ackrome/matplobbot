from fastapi import Request
from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware

from shared_lib.request_context import (
    CORRELATION_ID_HEADER,
    generate_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)
from shared_lib.telemetry import attach_correlation_id_to_span


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = (request.headers.get(CORRELATION_ID_HEADER) or "").strip()
        correlation_id = incoming or generate_correlation_id(prefix="http")
        token = set_correlation_id(correlation_id)
        attach_correlation_id_to_span(trace.get_current_span(), correlation_id)
        request.state.correlation_id = correlation_id
        try:
            response = await call_next(request)
        finally:
            reset_correlation_id(token)
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response

from aiogram import BaseMiddleware
from aiogram.types import Update
from opentelemetry.trace import SpanKind, Status, StatusCode

from shared_lib.request_context import (
    generate_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)
from shared_lib.telemetry import attach_correlation_id_to_span, get_tracer


def _resolve_update_kind(event: Update) -> str:
    if event.message:
        return "message"
    if event.callback_query:
        return "callback_query"
    if event.inline_query:
        return "inline_query"
    if event.edited_message:
        return "edited_message"
    return "update"


def _resolve_user_id(event: Update) -> int | None:
    if event.message and event.message.from_user:
        return event.message.from_user.id
    if event.callback_query and event.callback_query.from_user:
        return event.callback_query.from_user.id
    if event.inline_query and event.inline_query.from_user:
        return event.inline_query.from_user.id
    return None


def _resolve_chat_id(event: Update) -> int | None:
    if event.message and event.message.chat:
        return event.message.chat.id
    if event.edited_message and event.edited_message.chat:
        return event.edited_message.chat.id
    if event.callback_query and event.callback_query.message and event.callback_query.message.chat:
        return event.callback_query.message.chat.id
    return None


def _resolve_command(event: Update) -> str | None:
    if not event.message or not event.message.text:
        return None
    text = event.message.text.strip()
    if not text.startswith("/"):
        return None
    return text.split()[0]


class BotTracingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Update, data):
        correlation_id = generate_correlation_id(prefix="bot")
        token = set_correlation_id(correlation_id)
        tracer = get_tracer("bot.updates")
        update_kind = _resolve_update_kind(event)

        with tracer.start_as_current_span(
            f"telegram.{update_kind}",
            kind=SpanKind.SERVER,
        ) as span:
            span.set_attribute("messaging.system", "telegram")
            span.set_attribute("messaging.operation", "process")
            span.set_attribute("telegram.update.kind", update_kind)
            span.set_attribute("telegram.update.id", event.update_id)
            user_id = _resolve_user_id(event)
            chat_id = _resolve_chat_id(event)
            command = _resolve_command(event)
            if user_id is not None:
                span.set_attribute("telegram.user.id", user_id)
            if chat_id is not None:
                span.set_attribute("telegram.chat.id", chat_id)
            if command:
                span.set_attribute("telegram.command", command)
            attach_correlation_id_to_span(span, correlation_id)

            try:
                return await handler(event, data)
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
            finally:
                reset_correlation_id(token)

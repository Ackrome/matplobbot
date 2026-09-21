"""Private mailbox setup and persistent email delivery worker."""

import asyncio
import base64
import logging
import os
import time
from contextlib import suppress

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichMessage,
    ReplyParameters,
)
from sqlalchemy import select

from shared_lib.database import get_session
from shared_lib.mail_bridge import (
    PASSWORD_PROMPT,
    cipher,
    parse_mail,
    poll_mail,
    seal,
    unseal,
    validate_host,
)
from shared_lib.models import MailAccount, User

MAX_MAILBOXES_PER_USER = 10


class MailSetup(StatesGroup):
    details = State()
    password = State()


def keyboard(rows):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=value) for label, value in row]
            for row in rows
        ]
    )


class MailManager:
    def __init__(self):
        self.router = Router(name="mail")
        self.router.message.filter(F.chat.type == "private")
        self.router.callback_query.filter(F.message.chat.type == "private")
        self.router.message.register(self.menu, Command("mail"))
        self.router.message.register(self.cancel, Command("cancel"), StateFilter(MailSetup))
        self.router.callback_query.register(self.action, F.data.startswith("mail:"))
        self.router.message.register(self.details, MailSetup.details)
        self.router.message.register(self.password, MailSetup.password)
        self.router.message.register(
            self.expired_password, F.reply_to_message.text.startswith(PASSWORD_PROMPT)
        )

    async def expired_password(self, message):
        with suppress(Exception):
            await message.delete()
        await message.answer("Подключение истекло. Начните заново: /mail")

    async def cancel(self, message, state: FSMContext):
        await state.clear()
        await message.answer("Подключение почты отменено.")

    async def menu(self, message, state: FSMContext):
        await state.clear()
        try:
            cipher()
        except (KeyError, ValueError):
            await message.answer("Почта пока не включена администратором.")
            return
        async with get_session() as session:
            accounts = (
                await session.scalars(
                    select(MailAccount).where(MailAccount.user_id == message.from_user.id)
                )
            ).all()
        rows = [[(f"{a.address}: {a.status}", f"mail:show:{a.id}")] for a in accounts]
        if len(accounts) < MAX_MAILBOXES_PER_USER:
            rows.append([("Добавить ящик", "mail:add")])
        else:
            rows.append([(f"Лимит: {MAX_MAILBOXES_PER_USER} ящиков", "mail:limit")])
        await message.answer("Почтовые ящики", reply_markup=keyboard(rows))

    async def action(self, callback, state: FSMContext):
        await callback.answer()
        if callback.data == "mail:limit":
            await callback.message.answer(
                f"Достигнут лимит: {MAX_MAILBOXES_PER_USER} почтовых ящиков на пользователя."
            )
            return
        if callback.data == "mail:add":
            try:
                cipher()
            except (KeyError, ValueError):
                await callback.message.answer("Почта пока не включена администратором.")
                return
            async with get_session() as session:
                account_ids = list(
                    await session.scalars(
                        select(MailAccount.id)
                        .where(MailAccount.user_id == callback.from_user.id)
                        .limit(MAX_MAILBOXES_PER_USER + 1)
                    )
                )
                if len(account_ids) >= MAX_MAILBOXES_PER_USER:
                    await callback.message.answer(
                        f"Достигнут лимит: {MAX_MAILBOXES_PER_USER} почтовых ящиков на пользователя."
                    )
                    return
            await state.clear()
            await state.set_state(MailSetup.details)
            await callback.message.answer(
                "Введите адрес, сервер, порт и протокол через пробел.\nНапример: name@yandex.ru imap.yandex.ru 993 imap\nPOP3: name@mail.ru pop.mail.ru 995 pop3\nТолько SSL/TLS, без STARTTLS. /cancel для отмены."
            )
            return
        try:
            _, action, ident = callback.data.split(":")
            ident = int(ident)
        except ValueError:
            return
        async with get_session() as session:
            account = await session.scalar(
                select(MailAccount)
                .where(MailAccount.id == ident, MailAccount.user_id == callback.from_user.id)
                .with_for_update()
            )
            if account is None:
                await callback.message.answer("Ящик не найден.")
                return
            if action == "delete":
                await callback.message.answer(
                    "Удалить подключение и недоставленные письма? Сам почтовый ящик не изменится.",
                    reply_markup=keyboard(
                        [[("Удалить", f"mail:confirm:{ident}"), ("Назад", f"mail:show:{ident}")]]
                    ),
                )
                return
            if action == "confirm":
                await session.delete(account)
                await session.commit()
                await callback.message.answer("Подключение удалено.")
                return
            if action == "toggle":
                account.enabled = not account.enabled
                account.status = "ready" if account.enabled else "paused"
                await session.commit()
            await callback.message.answer(
                f"{account.address}\n{account.protocol.upper()} · {account.host}:{account.port}\nСтатус: {account.status}",
                reply_markup=keyboard(
                    [
                        [("Пауза" if account.enabled else "Возобновить", f"mail:toggle:{ident}")],
                        [("Удалить подключение", f"mail:delete:{ident}")],
                    ]
                ),
            )

    async def details(self, message, state: FSMContext):
        try:
            address, host, port_text, protocol = (message.text or "").split()
            port = int(port_text)
            if not 1 <= port <= 65535:
                raise ValueError()
            if len(address) > 320 or "@" not in address:
                raise ValueError()
            host = validate_host(host, protocol)
        except ValueError:
            await message.answer(
                "Нужны адрес, разрешённый сервер, порт от 1 до 65535 и imap либо pop3. Например: name@mail.ru imap.mail.ru 993 imap. Только SSL/TLS."
            )
            return
        await state.update_data(address=address, host=host, protocol=protocol, port=port)
        await state.set_state(MailSetup.password)
        await message.answer(
            PASSWORD_PROMPT
            + "\nОтветьте на это сообщение паролем приложения, не основным паролем. Он будет зашифрован на сервере. Сообщение с паролем удалим; Telegram не является секретным чатом. Пересылаются только новые письма, проверка каждые 30 секунд.",
            reply_markup=ForceReply(force_reply=True),
        )

    async def password(self, message, state: FSMContext):
        if not message.text or len(message.text) > 1024:
            await message.answer("Отправьте пароль приложения текстом.")
            return
        with suppress(Exception):
            await message.delete()
        data = await state.get_data()
        password = message.text
        await state.clear()
        try:
            checkpoint, _ = await asyncio.to_thread(
                poll_mail,
                data["host"],
                data["protocol"],
                data["address"],
                password,
                port=data["port"],
            )
            async with get_session() as session:
                # Serialize additions per user so concurrent password replies cannot
                # bypass the per-user cap between the count and INSERT statements.
                await session.scalar(
                    select(User.user_id)
                    .where(User.user_id == message.from_user.id)
                    .with_for_update()
                )
                accounts = (
                    await session.scalars(
                        select(MailAccount).where(MailAccount.user_id == message.from_user.id)
                    )
                ).all()
                if len(accounts) >= MAX_MAILBOXES_PER_USER or any(
                    a.address == data["address"] and a.host == data["host"] for a in accounts
                ):
                    await message.answer(
                        f"Этот ящик уже подключён или достигнут лимит: {MAX_MAILBOXES_PER_USER} ящиков."
                    )
                    return
                session.add(
                    MailAccount(
                        user_id=message.from_user.id,
                        **data,
                        credential=seal(password),
                        checkpoint=seal(checkpoint),
                    )
                )
                await session.commit()
        except Exception:
            # Never expose protocol errors: servers may echo the login or password.
            await message.answer(
                "Не удалось подключить ящик. Проверьте доступ IMAP/POP3 и пароль приложения. Повторить: /mail"
            )
            return
        await message.answer("Ящик подключён. Старые письма не пересылаются. Управление: /mail")


async def deliver_step(bot, account, pending):
    """Acknowledge one component at a time; caller persists before the next send."""
    reply = (
        ReplyParameters(message_id=pending["message_id"], allow_sending_without_reply=True)
        if pending["message_id"]
        else None
    )
    if pending["chunks"]:
        sent = await bot.send_rich_message(
            account.user_id,
            InputRichMessage(html=pending["chunks"][0], skip_entity_detection=True),
            reply_parameters=reply,
            request_timeout=60,
        )
        pending["message_id"] = pending["message_id"] or sent.message_id
        pending["chunks"].pop(0)
    elif pending["attachments"]:
        attachment = pending["attachments"][0]
        await bot.send_document(
            account.user_id,
            BufferedInputFile(base64.b64decode(attachment["data"]), filename=attachment["name"]),
            reply_parameters=reply,
            request_timeout=180,
        )
        pending["attachments"].pop(0)
    return bool(pending["chunks"] or pending["attachments"])


async def mail_worker(bot):
    """Poll without blocking the bot event loop; lock ownership across replicas."""
    if not os.getenv("MAIL_CREDENTIAL_KEY"):
        return
    cipher()
    next_check = {}
    while True:
        try:
            async with get_session() as session:
                ids = list(
                    await session.scalars(
                        select(MailAccount.id).where(MailAccount.enabled.is_(True))
                    )
                )
            for ident in ids:
                if next_check.get(ident, 0) > time.monotonic():
                    continue
                async with get_session() as session:
                    # One bounded network operation per transaction; SKIP LOCKED avoids
                    # duplicate delivery from concurrent bot instances.
                    account = await session.scalar(
                        select(MailAccount)
                        .where(MailAccount.id == ident, MailAccount.enabled.is_(True))
                        .with_for_update(skip_locked=True)
                    )
                    if account is None:
                        continue
                    try:
                        if not account.pending:
                            checkpoint, raw = await asyncio.to_thread(
                                poll_mail,
                                account.host,
                                account.protocol,
                                account.address,
                                unseal(account.credential),
                                unseal(account.checkpoint),
                                port=account.port,
                            )
                            account.checkpoint = seal(checkpoint)
                            if raw:
                                account.pending = seal(parse_mail(raw, account.address))
                        else:
                            pending = unseal(account.pending)
                            remaining = await deliver_step(bot, account, pending)
                            account.pending = seal(pending) if remaining else None
                        account.status = "delivering" if account.pending else "ready"
                        await session.commit()
                        next_check[ident] = time.monotonic() + (1.1 if account.pending else 30)
                    except Exception as exc:
                        await session.rollback()
                        logging.warning("Mail account %s failed (%s)", ident, type(exc).__name__)
                        next_check[ident] = time.monotonic() + max(
                            30, getattr(exc, "retry_after", 60)
                        )
                        account = await session.get(MailAccount, ident)
                        if account:
                            account.status = "retry: " + type(exc).__name__[:50]
                            await session.commit()
                await asyncio.sleep(1.1)
        except Exception as exc:
            logging.warning("Mail worker failed (%s)", type(exc).__name__)
        await asyncio.sleep(1)

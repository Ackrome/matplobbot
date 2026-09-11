"""TLS mailbox ingestion and encrypted, restartable Telegram delivery state."""

import base64
import imaplib
import json
import os
import poplib
import re
import ssl
from email import policy
from email.parser import BytesParser
from html import escape

from bs4 import BeautifulSoup
from cryptography.fernet import Fernet
from sqlalchemy import BigInteger, Boolean, Column, Integer, LargeBinary, String, UniqueConstraint

from shared_lib.models import Base

MAX_MAIL_BYTES = 35 * 1024 * 1024
PASSWORD_PROMPT = "Пароль приложения для почты"
HOSTS = {
    "imap.gmail.com": "imap",
    "pop.gmail.com": "pop3",
    "imap.yandex.ru": "imap",
    "pop.yandex.ru": "pop3",
    "imap.mail.ru": "imap",
    "pop.mail.ru": "pop3",
    "outlook.office365.com": "imap",
    "pop-mail.outlook.com": "pop3",
}


def sensitive_mail_update(event, data):
    message = event.message or event.edited_message
    if not message:
        return False
    reply = message.reply_to_message
    return str(data.get("raw_state", "")).startswith("MailSetup:") or bool(
        reply and (reply.text or "").startswith(PASSWORD_PROMPT)
    )


class MailAccount(Base):
    __tablename__ = "mail_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "address", "host", name="uq_mail_owner_address_host"),
    )
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    address = Column(String(320), nullable=False)
    host = Column(String(253), nullable=False)
    protocol = Column(String(8), nullable=False)
    credential = Column(LargeBinary, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    checkpoint = Column(LargeBinary, nullable=False)
    pending = Column(LargeBinary, nullable=True)
    status = Column(String(80), nullable=False, default="ready")


def cipher():
    return Fernet(os.environ["MAIL_CREDENTIAL_KEY"].encode("ascii"))


def seal(value):
    return cipher().encrypt(json.dumps(value, ensure_ascii=False).encode("utf-8"))


def unseal(value):
    return json.loads(cipher().decrypt(value))


def validate_host(host, protocol):
    # Custom endpoints are operator-approved, never arbitrary user-supplied URLs.
    allowed = dict(HOSTS)
    for item in os.getenv("MAIL_ALLOWED_HOSTS", "").split(","):
        if ":" in item:
            name, kind = item.strip().rsplit(":", 1)
            allowed[name.lower()] = kind
    host = host.strip().lower()
    if allowed.get(host) != protocol:
        raise ValueError("unsupported mail server")
    return host


def poll_mail(host, protocol, address, password, checkpoint=None):
    """Return a checkpoint and at most one new MIME message; never alter mail."""
    validate_host(host, protocol)
    context = ssl.create_default_context()
    client = None
    try:
        if protocol == "imap":
            client = imaplib.IMAP4_SSL(host, 993, ssl_context=context, timeout=30)
            client.login(address, password)
            if client.select("INBOX", readonly=True)[0] != "OK":
                raise ValueError("inbox unavailable")
            validity = client.response("UIDVALIDITY")[1][0].decode("ascii")
            kind, data = client.uid("search", None, "ALL")
            if kind != "OK":
                raise ValueError("mail listing failed")
            uids = sorted(int(v) for v in data[0].split())
            if checkpoint is None:
                return {"validity": validity, "uid": max(uids, default=0)}, None
            if checkpoint["validity"] != validity:
                raise ValueError("uidvalidity changed; reconnect mailbox")
            new = [uid for uid in uids if uid > checkpoint["uid"]]
            if not new:
                return checkpoint, None
            uid = new[0]
            kind, size_data = client.uid("fetch", str(uid), "(RFC822.SIZE)")
            size = re.search(
                rb"RFC822.SIZE (\d+)", b" ".join(x for x in size_data if isinstance(x, bytes))
            )
            if kind != "OK" or not size:
                raise ValueError("message size unavailable")
            next_state = {"validity": validity, "uid": uid}
            if int(size[1]) > MAX_MAIL_BYTES:
                return (
                    next_state,
                    b"Subject: Message exceeds 35 MiB limit\r\n\r\nOpen this message in your email client.",
                )
            kind, parts = client.uid("fetch", str(uid), "(BODY.PEEK[])")
            if kind != "OK":
                raise ValueError("message unavailable")
            raw = next(part[1] for part in parts if isinstance(part, tuple))
        else:
            client = poplib.POP3_SSL(host, 995, context=context, timeout=30)
            client.user(address)
            client.pass_(password)
            entries = [line.decode("ascii").split() for line in client.uidl()[1]]
            current = [uid for _, uid in entries]
            if checkpoint is None:
                return {"uids": current}, None
            seen = set(checkpoint["uids"])
            new = [(number, uid) for number, uid in entries if uid not in seen]
            if not new:
                return {"uids": current}, None
            number, uid = new[0]
            next_state = {"uids": [v for v in current if v in seen or v == uid]}
            size = int(client.list(int(number)).split()[2])
            if size > MAX_MAIL_BYTES:
                return (
                    next_state,
                    b"Subject: Message exceeds 35 MiB limit\r\n\r\nOpen this message in your email client.",
                )
            raw = b"\r\n".join(client.retr(int(number))[1])
        if len(raw) > MAX_MAIL_BYTES:
            raise ValueError("message size limit exceeded")
        return next_state, raw
    finally:
        if client is not None:
            try:
                client.logout() if protocol == "imap" else client.quit()
            except Exception:
                pass


def parse_mail(raw, address):
    """Build bounded rich HTML blocks and safe attachments without fetching URLs."""
    message = BytesParser(policy=policy.default).parsebytes(raw)
    header = "\n".join(
        (
            str(message.get("Subject", "(без темы)")),
            str(message.get("From", "")),
            address,
            str(message.get("Date", "")),
        )
    )[:2000]
    body = message.get_body(preferencelist=("html", "plain"))
    text = ""
    rich_body = None
    if body:
        try:
            text = body.get_content()
        except (LookupError, UnicodeError):
            text = (body.get_payload(decode=True) or b"").decode("utf-8", errors="replace")
        if body.get_content_type() == "text/html":
            soup = BeautifulSoup(text, "html.parser")
            for tag in soup(["script", "style", "head", "iframe", "object", "img"]):
                tag.decompose()
            for link in soup.find_all("a"):
                href = link.get("href", "")
                if href.startswith(("https://", "http://", "mailto:")):
                    link["href"] = href
                else:
                    link.unwrap()
            allowed = {
                "p",
                "br",
                "b",
                "strong",
                "i",
                "em",
                "u",
                "s",
                "code",
                "pre",
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
                "ul",
                "ol",
                "li",
                "blockquote",
                "table",
                "tr",
                "th",
                "td",
                "a",
            }
            for tag in list(soup.find_all(True)):
                if tag.name not in allowed:
                    tag.unwrap()
                else:
                    tag.attrs = (
                        {"href": tag["href"]} if tag.name == "a" and tag.has_attr("href") else {}
                    )
            rich_body = str(soup)
            text = soup.get_text("\n", strip=True)
    # Split before escaping, so HTML entities and Unicode code points stay intact.
    chunks = ["<p><b>" + escape(header) + "</b></p>"]
    text = str(text)
    if rich_body and len(rich_body) <= 8000:
        chunks[0] += rich_body
    else:
        chunks.extend(
            "<p>" + escape(text[i : i + 2500]) + "</p>"
            for i in range(0, min(len(text), 100000), 2500)
        )
    if len(text) > 100000:
        chunks.append("<p>Текст сокращён. Полное письмо доступно в почтовом клиенте.</p>")
    attachments = []

    def file_parts(part):
        if (
            part.get_filename()
            or part.get_content_disposition() == "attachment"
            or part.get_content_type() == "message/rfc822"
        ):
            yield part
        elif part.is_multipart():
            for child in part.iter_parts():
                yield from file_parts(child)

    for part in file_parts(message):
        if part.get_content_type() == "message/rfc822":
            payload = b"\r\n".join(item.as_bytes() for item in part.get_payload())
        elif part.is_multipart():
            payload = part.as_bytes()
        else:
            payload = part.get_payload(decode=True)
        if payload is None:
            continue
        name = re.split(r"[/\\]", part.get_filename() or "attachment.bin")[-1]
        name = re.sub(r"[\x00-\x1f\x7f]", "_", name)[:180] or "attachment.bin"
        attachments.append({"name": name, "data": base64.b64encode(payload).decode("ascii")})
    return {"chunks": chunks, "attachments": attachments, "message_id": None}

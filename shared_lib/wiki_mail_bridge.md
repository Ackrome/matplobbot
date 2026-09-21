# Mail Bridge

`mail_bridge.py` owns Fernet encryption,
TLS IMAP/POP3 ingestion and MIME-to-rich-HTML conversion.

The `MailAccount` SQLAlchemy model lives in `shared_lib/models.py`, keeping
metadata and its cascading user foreign key in the central model registry.

Public entry points: `seal`/`unseal` protect JSON credentials and delivery state;
`validate_host` enforces the operator's server allowlist; `poll_mail` returns
one message plus its next checkpoint; `parse_mail` returns rich HTML chunks and
base64 attachment bytes. `sensitive_mail_update` suppresses password input logs.

Example: `checkpoint, raw = poll_mail(host, 'imap', address, password)` establishes
a baseline without downloading history. Pass that checkpoint on subsequent calls.
Run blocking protocol calls in `asyncio.to_thread`, never on the bot event loop.

Dependencies: standard-library email/imaplib/poplib/ssl, BeautifulSoup,
cryptography, SQLAlchemy. `MAIL_CREDENTIAL_KEY` must be a persistent Fernet key.
Additional trusted servers use `MAIL_ALLOWED_HOSTS=host.example:imap,host2:pop3`.
The bot handler allows up to ten mailboxes per Telegram user.
`poll_mail(..., port=1993)` uses an explicit port (1-65535), defaulting to
993/995 when omitted. All ports require implicit TLS, not STARTTLS.
Never weaken certificate validation.

Side effects: connects to mail servers but never deletes mail or marks it read.
No remote HTML assets are fetched. A 35 MiB raw-message cap protects memory;
oversize messages produce a notice instead. HTML over 8000 characters falls
back to escaped text; body text above 100000 characters is explicitly truncated.
UIDVALIDITY changes fail closed: reconnect to establish a new baseline.
Schema changes must update the Alembic migration. The pending encrypted payload
is temporary storage, not a permanent email archive.

# Mail Bot Integration

`mail.py` provides `MailManager`, `mail_worker(bot)` and
`run_mail_worker_with_retry(bot)`. The router exposes `/mail`
in private chats: add up to ten mailboxes, inspect status, pause/resume, delete
with confirmation. Connection setup uses aiogram FSM, deletes the password
message best-effort, and never places the password in FSM storage.
Setup format: `name@yandex.ru imap.yandex.ru 993 imap`. The port is required,
persisted and displayed in account details; only implicit TLS is supported.

Example: register `MailManager().router` ahead of general text handlers and run
`run_mail_worker_with_retry(bot)` as a managed background task. `bot/main.py`
does both. The supervisor restarts the worker after an unexpected task-level
failure and re-raises normal cancellation during shutdown.
The bot must receive `MAIL_CREDENTIAL_KEY`; absent key disables ingestion.

Dependencies: shared mailbox model, async SQLAlchemy sessions, aiogram rich
messages and document uploads. PostgreSQL row locks serialize delivery across
replicas. Only the account owner can inspect/change/delete the connection.

Side effects: network login, encrypted database writes, private Telegram sends.
Each acknowledged part is removed from pending storage before the next send.
Failed uploads preserve bytes. Progress survives restart. Telegram API lacks
idempotency keys: a lost response or crash before commit can cause a duplicate.
Deletion removes pending content and credentials; it cannot retract existing
Telegram messages or database backups/WAL. Users should revoke app passwords
at their provider as well. Telegram bot chats are not end-to-end encrypted.

Rich delivery first uses the sanitized HTML component. If Telegram rejects that
component with `TelegramBadRequest`, the handler sends one escaped paragraph
derived from the same component and advances the same pending state only after
that fallback is acknowledged. This keeps malformed provider HTML from
creating an endless retry loop.

Maintenance: polling is approximately every 30 seconds, not IMAP IDLE; network
latency and account count extend it. One worker processes accounts sequentially.
Retry delays honor Telegram retry_after with a 30-second minimum. The supervisor
restarts a task that exits unexpectedly, so a transient task-level failure does
not require a bot restart. Permanent
authentication errors require reconnecting; UI shows the exception class only.
Add tests when changing checkpoint, redaction, partial-delivery or ownership logic.

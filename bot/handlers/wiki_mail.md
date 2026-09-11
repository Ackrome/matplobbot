# Mail Bot Integration

`mail.py` provides `MailManager` and `mail_worker(bot)`. The router exposes `/mail`
in private chats: add up to five mailboxes, inspect status, pause/resume, delete
with confirmation. Connection setup uses aiogram FSM, deletes the password
message best-effort, and never places the password in FSM storage.

Example: register `MailManager().router` ahead of general text handlers and run
`mail_worker(bot)` as a managed background task. `bot/main.py` does both.
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

Maintenance: polling is approximately every 30 seconds, not IMAP IDLE; network
latency and account count extend it. One worker processes accounts sequentially.
Retry delays honor Telegram retry_after with a 30-second minimum. Permanent
authentication errors require reconnecting; UI shows the exception class only.
Add tests when changing checkpoint, redaction, partial-delivery or ownership logic.

# Mail Regression Tests

`test_mail_bridge.py` uses unittest and mocked protocol/Telegram clients. Run
`python -m unittest discover -s tests -p test_mail_bridge.py -v` from the root
with project `.venv` Python. No live mailboxes, credentials or Telegram messages
are used. Tests cover encryption, host restrictions, MIME sanitization, initial
IMAP/POP3 baselines, secret detection and failed/successful attachment cleanup.

Handler code is loaded directly to avoid unrelated legacy library import-time
network requests. These tests do not replace a PostgreSQL locking integration
test or an opt-in live mailbox/Telegram acceptance test.

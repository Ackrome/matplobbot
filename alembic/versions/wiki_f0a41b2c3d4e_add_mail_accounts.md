# Mail Accounts Migration

`upgrade()` creates `mail_accounts`, its owner index and unique owner/address/host
constraint. `downgrade()` removes the table and permanently discards mailbox
connections and pending deliveries. Dependencies: Alembic and SQLAlchemy.

Apply using `.venv` Python: `python -m alembic upgrade head` before enabling the
mail worker. This follows `a0b5a060b6fe`; never rewrite an applied migration.
Encrypted credentials, checkpoints and pending MIME components use binary columns.

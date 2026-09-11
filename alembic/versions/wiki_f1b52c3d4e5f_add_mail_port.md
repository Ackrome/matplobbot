# Mail Port Migration

`upgrade()` adds the non-null mailbox port, backfilling existing IMAP accounts
with 993 and POP3 accounts with 995. `downgrade()` discards custom port settings.
Run `python -m alembic upgrade head` before deploying the updated bot.
Dependencies: Alembic and SQLAlchemy. No credential or checkpoint changes.

# Session refresh errors migration

`upgrade()` adds the optional `last_error` column to existing Session date snapshots.
It preserves verified dates and timestamps. Existing rows start with no recorded
error. The scheduler writes a fixed error code after failure and clears it on retry.

Run `python -m alembic upgrade head` using the application database settings.
`downgrade()` removes the error column. It leaves term snapshots and verification
times in place. The revision requires the preceding Studio migration and uses
Alembic's SQLAlchemy operations.

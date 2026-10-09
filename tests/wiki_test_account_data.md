# Account ownership and deletion tests

`test_account_data.py` validates exports, Telegram-only deletion, full account cascades and JWT rejection after erasure. `TestAccountData` creates a fresh in-memory SQLite database with foreign keys enabled and two independent owners, using production SQLAlchemy model definitions. A small async adapter executes real relational statements without introducing a new test dependency. Redis cleanup is mocked; live services and production data are never accessed.

Run `.venv/Scripts/python.exe -m unittest tests.test_account_data -v`. Assertions cover owned projects/assets, credential exclusion, preservation of the other owner's data, complete foreign-key erasure, and website access after Telegram-only cleanup. SQLite does not prove PostgreSQL transaction isolation or Alembic migrations, so retain PostgreSQL migration/integration checks separately. New owner tables must extend these fixtures and export checks.

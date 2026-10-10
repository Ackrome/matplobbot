# Auth sessions regression tests

`AuthSessionTests` uses real SQLite SQLAlchemy persistence and FastAPI HTTP
requests to verify current-session logout, account-wide logout, password rotation,
expired revocation cleanup and REST/WebSocket rejection. It also checks existing
stream revalidation. SQLite validates these behaviors, not PostgreSQL concurrency.
`LoginLimitTests` exercises trusted proxy identity, stable hashed shared keys and
fail-closed handling before password lookup. Redis Lua itself is exercised by the
release integration harness; its client is mocked in this fast unit suite.

Run `.venv/Scripts/python.exe -m unittest tests.test_auth_sessions -v` from the
project root. Requires FastAPI, SQLAlchemy, JWT and test dependencies. Creates only
an in-memory database, synthetic credentials and temporary mocks. Keep HTTP tests
using the real authentication dependency; bypassing it would hide revocation bugs.

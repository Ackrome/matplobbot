# test_curriculum_session.py

`TestCurriculumSessionDates` exercises Session dates with real SQLAlchemy
statements in an isolated SQLite database and a stub RUZ client. It covers the
per-tick request cap, retry ordering, preservation of verified dates on a
failed refresh, term isolation, canonical evidence precedence, date-free result
states and strict matching of general credit rows. The migration smoke test
applies and reverses the Session snapshot revision.

From the repository root run `python -m unittest tests.test_curriculum_session`.
The suite uses the shared SQLAlchemy test adapter in `test_curriculum_service.py`
and the standard Alembic migration harness. It makes no network requests and
does not touch a real database. SQLite verifies statement behavior; validate
locking and release migration on PostgreSQL through the usual acceptance suite.

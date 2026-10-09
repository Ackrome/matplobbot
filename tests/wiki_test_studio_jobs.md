# Studio job regression tests

`test_studio_jobs.py` exercises the async job API with FastAPI TestClient and controlled Redis/Celery doubles.

Run `.venv/Scripts/python.exe -X utf8 -m unittest tests.test_studio_jobs -v` from the repository root.

Tests cover metadata-before-publication, nonblocking 202 responses, Markdown task arguments, closed publication on Redis failure, owner/expiry isolation, retrieval after a new client session, deduplication keys, input validation and redaction of worker exceptions/build cache. Dependencies are FastAPI, the shared task imports and unittest mocks. No live broker, database, rendering process or Telegram call is used.

Maintain transport/result contracts when updating the client. These tests do not substitute for a production worker compile or PostgreSQL migration verification.

Project-format routing and cache persistence are tested too: cache bytes are stored
only for a matching source snapshot, and never exposed through the public job API.

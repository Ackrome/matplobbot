# test_studio_archive.py

`TestStudioArchive` runs the normal export, preview and import routes against
SQLite and real ZIP fixtures. It checks filename preservation, UTF-8, binary
and empty assets, the main file, checksum-bound private previews, legacy ZIP
choices, unsupported inputs, quota boundaries and atomic rollback.

Use `python -m unittest tests.test_studio_archive` from the project root. The
suite also tests an authenticated oversized request without Content-Length
and proves an unauthenticated request reaches the auth error without reading
the stream. It uses the Studio version SQLAlchemy test adapter and an in-memory
database. Production concurrency remains covered by PostgreSQL integration.

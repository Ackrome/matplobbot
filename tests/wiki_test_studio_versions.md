# test_studio_versions.py

Tests owner isolation, stable named snapshots, restored compile inputs, failure
rollback, quotas and the migration. `TestStudioVersions` mounts the same Studio
project, version and build routes used by the app. The relational fixture runs
SQLAlchemy statements on SQLite, adapts `octet_length`, and stops the queued
build at the enqueue boundary. Legacy paths and binary bytes are checked in the
normal restored-project compile request.

Run `python -m unittest tests.test_studio_versions` from the project root.
The fixture does not contact Redis or compile a real document. Use PostgreSQL
integration to validate row locks, concurrent quota enforcement and migration
under production-like conditions when changing those paths.

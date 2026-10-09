# test_curriculum_service.py

Supplement tests cover independently paginated source snapshots, exact parent
scope and one-level restrictions, unpublished candidates, duplicate titles
across root/child and child/child sources, root-only group bindings, explicit
semester calendars, preserving reviewed child PDFs on replacement, unrelated
and malformed cross-cohort links, and root deletion retaining unbound children.
Deletion runs both through the service without SQLite FK enforcement and through
direct SQL with enforcement enabled. Migration round-trip includes
`fc2c3d4e5f60`, verifies its revision chain, self-FK `ON DELETE SET NULL`, index and
model parity. No real official assessments are hardcoded as test answers.

Profile tests cover validation/reset, a setting before first import, cached
reprocessing without downloads, preservation of publication, no-op repetition,
and discarding stale worker success/failure after profile changes (including
change-and-reset while the old lease is active). Migration parity also applies
`fb1b2c3d4e5f` and downgrades it before earlier migrations.

Background OCR regressions cover durable staging, publication blocked while queued, source-hash/model-version caching, unchanged-byte human correction preservation, safe timeout error and cached retry, cancelled lease recovery, global active-worker serialization, stale results after a replacement, and excluding OCR previews from published/public facts. Migration parity runs both the source migration and `fa0a1b2c3d4e`, then downgrades them in reverse order. SQLite checks statements and rollback behavior; PostgreSQL concurrent lock contention is not simulated.

Exercises actual SQLAlchemy persistence and domain behavior for official curriculum review using isolated in-memory SQLite. The small `_AsyncSession` adapter runs the production statements unchanged without introducing a test-only asynchronous database driver. PostgreSQL concurrency semantics are not emulated.

`TestCurriculumPersistence` covers staged imports requiring publication, exact title/group scope, explicit date-to-semester mapping, coexisting and multi-term assessment forms, ambiguous discipline codes, failed/changed/unchanged source refreshes, preserved published PDF provenance, optimistic publish hash checks, source-page validation, group collisions/removal, document deletion, due-date persistence, fortnightly configuration and refresh leases. Downloader/parser functions are mocked with clearly synthetic PDF bytes; these tests do not assert factual university curriculum data.

`TestCurriculumMigration` executes the new Alembic migration in both directions, checks model column parity, and re-applies it.

Run with the project interpreter: `.venv/Scripts/python.exe -m unittest tests.test_curriculum_service -v`. Dependencies: unittest, SQLAlchemy and Alembic plus normal project imports. Tests create no network traffic, production database writes or filesystem artifacts. Update fixtures/contracts together with `curriculum_service`; preserve the cases preventing a newer PDF or a different campus/cohort from silently changing published facts.

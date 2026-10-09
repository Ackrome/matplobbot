# f9f0a1b2c3d4_add_curriculum_documents.py

Adds persistent official-document review state and explicit group-to-curriculum bindings after revision `f8e9f0a1b2c3`.

`upgrade()` creates `curriculum_documents` with identity metadata, staged PDF bytes/hash/parsed candidates, independently published PDF bytes/hash/reviewed assessments, refresh lease state, success/error timestamps and an indexed next-check date. It creates `curriculum_groups`, keyed globally by RUZ group ID, with a cascading document foreign key, display name and reviewed semester-date JSON. The document ID index supports mapping lookups.

`downgrade()` drops bindings first, then documents. This removes imported documents and their published facts, so normal production rollback should be coordinated with application rollback and backups.

Usage: run `alembic upgrade head` before starting API/scheduler code using this feature. Dependencies are Alembic and SQLAlchemy; all database changes are made through Alembic operations. Keep columns synchronized with `CurriculumDocument` and `CurriculumGroup` in `shared_lib.models`. `TestCurriculumMigration` executes upgrade/downgrade/re-upgrade and compares model columns on SQLite; production uses PostgreSQL.

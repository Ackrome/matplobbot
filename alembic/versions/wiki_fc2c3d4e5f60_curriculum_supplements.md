# Separately reviewed supplementary curriculum sources

`fc2c3d4e5f60_curriculum_supplements.py` follows `fb1b2c3d4e5f` and adds the
nullable indexed `curriculum_documents.parent_document_id` self-reference.
`upgrade()` creates its named foreign key with `ON DELETE SET NULL`.
`downgrade()` drops the index, constraint and column while retaining document
rows and their published PDF snapshots. Removing the link loses supplement
associations, so recreate reviewed bindings explicitly after an upgrade.

Run through the project Alembic environment with `alembic upgrade head`.
Dependencies are Alembic and SQLAlchemy. Batch operations support SQLite test
databases; PostgreSQL executes schema changes normally. Existing documents
remain roots because the new field is null. The migration does not infer
parents or publish records. Application validation restricts links to one
level and matching programme, profile, campus, admission year and study form.
Groups are attached only to roots. The service also explicitly unlinks children
on deletion for SQLite clients without foreign-key enforcement.

`TestCurriculumMigration` checks migration order, schema parity, indexes and
foreign-key metadata. Persistence regressions check deletion with SQLite foreign
keys both enabled and disabled. Keep the model, service and migration names in
sync; this link must never replace each source's own URL, hash, page or PDF.

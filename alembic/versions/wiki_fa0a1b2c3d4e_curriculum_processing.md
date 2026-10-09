# fa0a1b2c3d4e_curriculum_processing.py

Adds the durable background parsing queue and parser/model cache metadata to `curriculum_documents`. `upgrade()` adds source/parsed hashes, parser and engine versions, parse method, queue state, lease token/start and sanitized error. The processing-state index supports queue inspection. Existing PDF sources are marked queued and receive their current pending/published hash; reviewed facts remain unchanged.

Run through the normal Alembic upgrade after `f9f0a1b2c3d4`. The scheduler processes migrated sources after startup. `downgrade()` removes only these new columns/index, retaining documents, published facts and group mappings.

Dependencies are SQLAlchemy and Alembic. Side effects are schema changes and one metadata backfill; no PDF parsing or network access occurs during migration. Preserve model parity and round-trip tests in `test_curriculum_service.py`. Source hash plus parser/model version defines cached work; lease expiration must exceed the worker's hard maximum wall time.

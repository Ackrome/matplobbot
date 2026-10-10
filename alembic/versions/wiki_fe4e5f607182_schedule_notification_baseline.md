# Schedule notification baseline migration

`upgrade()` creates the independently versioned notification snapshot table and
the indexed nullable `failed_at` delivery timestamp. Existing valid cached
schedules seed the baseline in batches of 500; formatter-only `date_obj` fields
are removed before hashing. A nullable legacy cache timestamp falls back to the
migration time for its baseline, without changing the cache's freshness. Existing failures keep a null timestamp, so deployment
does not falsely announce them as new failures. `downgrade()` removes these additions.

Stop the old scheduler before `alembic upgrade head`, then start the updated scheduler.
This prevents an old scan committing between backfill and new scanner startup. This revision
depends on `fd3d4e5f6071`, SQLAlchemy and Alembic; it has database/schema side effects
only and never sends messages. Preserve the migration's inline normalization and
hashing so future application changes cannot alter old migrations. An already lost
historical payload cannot be reconstructed from its hash; the migration starts
reliable comparisons from the best existing snapshot. Rollback discards the new
baseline and recent-failure timestamps, so prefer forward repair when possible.

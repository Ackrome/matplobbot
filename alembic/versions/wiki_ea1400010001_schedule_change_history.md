# Schedule change history migration

`upgrade()` creates an initially empty, indexed table for recent public lesson
changes. It neither backfills speculative events nor changes existing schedule,
notification or recipient records. `downgrade()` drops the history table and its
indexes. Run via `alembic upgrade head` in the existing release migration flow.

The runtime schema mirrors `shared_lib.models.ScheduleHistoryEntry`. Keep the
event and position uniqueness constraint when evolving the table. The scheduler
writes this table alongside its source checkpoint and cleans old entries.

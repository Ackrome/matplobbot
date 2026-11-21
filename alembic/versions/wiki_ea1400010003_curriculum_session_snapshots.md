# ea1400010003_curriculum_session_snapshots.py

Alembic `upgrade()` creates the PostgreSQL table for RUZ Session verification.
It stores a group ID, explicit semester dates, attempt timestamp, successful
check timestamp and projected assessment events. `downgrade()` drops the table.
It leaves the reviewed curriculum and canonical timetable tables intact.

Run `alembic upgrade head` in the normal deployment migrator. The revision
depends on `ea1400010002` and references `curriculum_groups`. Deleting a group
binding cascades to its date snapshots. Changing the dates produces a distinct
snapshot identity, so prior ranges cannot be treated as verified for the new
term. The scheduler builds new evidence after upgrade. The rollback removes
date-verification evidence for this feature, which the scheduler will rebuild
after another upgrade. Keep the schema consistent with `CurriculumSessionSnapshot`.

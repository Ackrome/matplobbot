# Verified schedule history

`build_schedule_history(old, new, semester_start=..., semester_end=...)` projects
university lessons to public fields and describes additions, cancellations, moves
and replacements. For example, a stable lesson ID with a different room or lecturer
produces a replacement with complete before/after views. It uses Moscow dates and
ignores old-semester rollover and non-display metadata. An ambiguous ID is omitted
from the link, and unmatched changes remain separate.

`read_schedule_history(type, id, event_key=None)` reads the latest 50 changes within
30 days; an event key selects one poll. Each accepted transition records at most
2,000 changes. `prune_schedule_history()` deletes one batch
of expired entries and is called by scheduler maintenance. Both use Async SQLAlchemy
and the shared PostgreSQL model. The scheduler persists deltas with the compare-and-swap
baseline and Telegram outbox in the same transaction. There is no retrospective
backfill.

History stores university timetable facts only. Keep account, chat, token and email
fields outside the projection and API. Register new source kinds only when their
timetables are already publicly accessible.

# Telegram schedule planning

`SchedulePlanningManager` in `schedule_planning.py` exposes `/plan`, `/conflicts`
and `/free` in private chats. `plan(message)` uses the caller's active
subscriptions and current `/myschedule` exclusions, then reports seven days of
overlaps and common 30-minute windows between 08:00 and 22:00 Moscow time.
`ScheduleManager` includes its router; the help menu links to `/plan`.

Example: subscribe to two groups, exclude irrelevant modules through existing
profile settings, then send `/plan`. Shared lessons are deduplicated. If a source
is still refreshing, repeat after refresh; unverified data never creates free
windows. Large result sets are explicitly shortened in Telegram; the website
exposes the bounded complete result.

Dependencies: aiogram, personal filter service, shared planning loader,
translation service, Redis cooldown and HTML-safe message splitting. Side
effects: private Telegram replies, five-second per-user cooldown, source/cache
reads. Group calls return before reading private subscriptions, including help
callbacks that bypass router filters. Escape all source titles and retain this
ownership boundary. Tests cover private filters and direct group invocation.

# Daily schedule occurrence rules

`schedule_daily.py` contains pure daily-delivery identity rules. `daily_occurrence`
finds the latest scheduled wall-clock occurrence in the subscription timezone,
including the previous local day, and returns its target date and expiry.
`daily_event_key` hashes entity plus target date; the outbox unique constraint adds
the application user. `deduplicate_daily_recipients` prefers the private chat,
then the lowest profile ID, across overlapping profiles.

Example: at 01:00 Moscow, a missed 23:30 notification targets the current date,
not the following date. `daily_occurrence(time(23, 30), "Europe/Moscow", now_utc)`
returns that original occurrence within the default six-hour window.

Dependencies: Python datetime, zoneinfo, hashlib. No I/O or mutation. Aware UTC
input is required; an invalid stored timezone falls back to Moscow. Catch-up is
bounded below 24 hours. Maintain date-based identity independently of run time,
profile ID and retry attempt so restart/overlapping schedules do not resend a day.

Regression coverage: `tests/test_schedule_delivery.py`.

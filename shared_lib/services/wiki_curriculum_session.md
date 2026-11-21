# curriculum_session.py

`cached_session_dates(group_id, term, assessments)` reads verified RUZ dates for
one reviewed group/semester. The HTTP path reads PostgreSQL only. Its result
contains `dates_status`, `dates_coverage`, `dates_checked_at` and matched `events`.
For example, use a reviewed term with `semester=5`, `start_date="2026-09-01"`
and `end_date="2027-01-25"` and the published rows for semester 5.

Coverage contains inclusive start and end dates and a UTC `checked_at`
timestamp. Before the first successful full-term check, the service can use
the verified overlap from the canonical timetable. After that, the durable
term snapshot is authoritative through timetable cache rollover. The next
successful term check atomically replaces its predecessor, including a
successful empty check. `checked` means the whole term was checked within six
hours, `stale` means full coverage with an older timestamp, `partial` means
only part of the term was checked, and `unavailable` means no verified
coverage. Only known assessment events with an explicit day and starting time
appear in `events`. Events can expose an unambiguous RUZ OID as `lesson_id`.

`refresh_session_dates(ruz_session)` is the scheduler entry point. It considers
explicitly mapped groups with a published root plan and terms active now or
starting within 45 days. Each 15-minute tick selects at most 8 due terms by
oldest attempt, with one bounded request per term. Requests stop at the reviewed
term boundaries and the maximum span of 185 days. Successes are reused for six
hours. Failures wait one hour before retry and preserve previous successful
evidence. A database row lock serializes claims. The completed request may only
write the result of its own claim.

The service uses the RUZ client, curriculum matching, SQLAlchemy and the
existing canonical timetable coverage. It stores a separate term snapshot of
assessment rows and timestamps, with no lecturer details. It leaves the
canonical timetable untouched. Run `python -m unittest tests.test_curriculum_session
tests.test_curriculum_api` when changing coverage, scheduling or publication
matching. Keep frontend status handling compatible with the API when editing the
coverage contract.

`admin_session_coverage()` reads the scheduler snapshots for current terms and
terms beginning within 45 days. Status is checked, stale or pending, independently
of the latest attempt's short error code. A rejected or failed refresh
leaves the last successful data and date range available.

`admin_session_reviews(group_id, semester)` reports only events from a
successful durable snapshot that have several eligible approved plan rows.
`confirm_session_review(group_id, term, event_key, review_key, candidate_key,
expected_selected)` takes locks on the current approved evidence, checks all
identities and updates that snapshot's `date_resolutions`. The event key binds
its public date, time, room and RUZ identity. The review key binds the complete
set of candidate rows to their approved document hashes. A changed event,
term, document or competing confirmation needs another review. The public
matcher still uses automatic exact matches when there is one eligible row.
A manual selection affects presentation of the observed date for that group
and term. It does not update the plan, calendar feed or the RUZ timetable.

# Schedule session dialog

`schedule_session.js` connects the schedule toolbar to the public group assessment
API. Choose a group on `/schedule`, open Assessments and select a semester.
`fetchSession()` first retrieves reviewed forms, then reads cached RUZ dates.
`load()` aborts obsolete requests on a semester switch or when the dialog closes.
`render()` links to hash-addressed PDF pages and groups form types by discipline.

The script uses the schedule page state, the shared RU/EN loader and a native
`dialog`. Dates come from the API's inclusive coverage ranges and include a
verification timestamp in Moscow time. Undated forms remain visible during
partial coverage or an outage. A dated link opens the exact timetable occurrence
when its RUZ lesson ID is unique on that date, or focuses the linked day when the
ID is missing or ambiguous. The calendar action opens an editable, per-group
exam and assessment subscription draft. A user must explicitly save it.
Keep the date request independent so the reviewed list stays usable if dates fail.

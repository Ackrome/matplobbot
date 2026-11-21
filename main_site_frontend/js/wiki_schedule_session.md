# Schedule session dialog

`schedule_session.js` connects the schedule toolbar to the public group assessment
API. Choose a group on `/schedule`, open Assessments and select a semester.
`fetchSession()` first retrieves reviewed forms, then requests published dates.
`load()` aborts obsolete requests on a semester switch or when the dialog closes.
`render()` links to hash-addressed PDF pages and groups form types by discipline.

The script uses the schedule page state, the shared RU/EN loader and a native
`dialog`. Opening the dialog is read-only from the user's perspective. The API
may populate its schedule cache while checking RUZ dates. Keep the date request
independent so the reviewed list stays usable during an upstream outage.

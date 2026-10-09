# Curriculum administration controller

`curricula.js` renders the `/curricula` workspace. `request` attaches the current
JWT, checks account changes, bounds requests, and handles JSON/PDF responses.
`load` retrieves administrator-only document state; `renderPlan` builds review
and group forms. `addAssessment`, `addGroup`, and `addTerm` create editable rows.
`handleAction` coordinates source refresh, document download and row operations.

Example workflow: create programme metadata and official URL, fetch/upload the
PDF, review each course/semester/assessment/page/evidence row, publish using the
candidate hash, then bind group IDs to explicit semester date ranges. Document
deletion removes mappings and stops source refreshes.

Dependencies: `mpbI18n` (central `curricula.*` RU/EN keys), `getMpbApiBase`, native
fetch/FormData and browser form validation. The API validates all input again.
PDFs are downloaded as temporary Blob URLs with authorization. API-provided text
is escaped before rendering. Source links are restricted to official FA URLs.

Side effects are explicit API mutations; translations do not clear entered
values. Dirty forms warn before losing edits. No document state is placed in
localStorage. Preserve the distinction between pending and published PDFs: an
unreadable replacement must not inherit the previous PDF's assessment rows.

Maintenance: keep semester/size bounds consistent with the API; support 204 on
deletion, surface failed-import detail states, and use the published hash when
correcting an already published version. Review desktop/mobile, RU/EN and dark
theme in Playwright after changes; version assets and dictionaries together.

## Background scan recognition

The registry fetch is lightweight; selecting a plan loads its authenticated
`GET /curricula/{id}` detail. Fetch/upload and CPU processing are distinct states.
`schedulePoll` checks only the selected queued/processing document, stops on
selection changes, hidden pages, navigation or logout, and retries transient
errors with a longer delay. `stopPolling` invalidates in-flight responses and
aborts their requests. A ready/error result cannot overwrite dirty or focused
review/group forms: `incomingPlan` waits for an explicit “Show new results”.
Publication stays disabled until processing and any result replacement finish.
`POST /{id}/reprocess` retries the saved PDF without downloading it again.
Ready drafts with `ocr_timeout:` warnings also expose retry, because a partial
OCR timeout is a recoverable manual-review outcome rather than a failed job.
Warnings retained from an earlier attempt never offer retry while a new job is
queued or processing.

OCR candidates remain drafts. `rowPreviews` keeps trusted provenance separate
from editable inputs; publication explicitly serializes only the six supported
assessment fields, never client-supplied OCR metadata. `validCrop` accepts only a
bounded base64 PNG with plausible IHDR dimensions. `showPreview` creates one
image on demand inside a native modal dialog; it is removed on close. Focus is
contained, Escape works, focus returns to the triggering row, and narrow-screen
image overflow stays inside a keyboard-scrollable region. Raw confidence never
becomes a factual verification label.

When modifying this workflow, check queue completion during editing, stale
responses after switching plans, partial polling failures, authentication loss,
engine-unavailable/manual fallback and the unchanged publish payload. Keep the
background processing error messages distinct from source-download failures.

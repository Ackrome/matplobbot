# Studio browser controller

`studio.js` binds the existing Studio page to account-scoped drafts, project/file operations,
on-demand previews, and asynchronous build jobs. It uses `studio_session.js` for durable state,
`studio_libraries.js` for pinned preview dependencies, and `studio-editor.html` for Monaco.

## Main flows

- `transition(action)` serializes project/file/mode changes and flushes the previous document
  before changing IDs. `saveCurrentFile()` rejects failed requests; build/export/send stop when
  saving fails. Every input is journaled locally; storage failure is reported without losing RAM
  contents. Quick snippets have independent drafts for each format.
- `activateDocument()` restores matching drafts and asks before replacing a newer server version
  with an older local draft. This is local recovery, not server revision history.
- `upgradeEditor()` retains an editable textarea until the same-origin Monaco frame is ready.
  The frame isolates AMD globals from lazy UMD preview libraries. CDN failure offers Retry.
- `compileCurrent()` submits `POST /api/studio/jobs` with `{type, content}` or
  `POST /api/studio/projects/{id}/jobs`; `pollJob()` reads `/api/studio/jobs/{job_id}`. Only actual
  queued/running states are shown. Job metadata survives reload within the account namespace;
  server results expire after 24 hours. Text remains editable while the job runs.
- `updateLivePreview()` lazily loads Markdown/KaTeX or Mermaid. DOMPurify sanitizes Markdown and
  SVG; Mermaid uses strict mode and SVG text labels. Request generations discard stale previews.
- `setupSplit()`/`switchMobileTab()` handle desktop panes and mobile tabs. File buttons, upload,
  tab navigation, status announcements, and project-modal focus are keyboard accessible.

## Usage

Open `/studio`, edit a quick draft or switch to Project. Editing is saved locally immediately;
project autosave follows after a short debounce. On an error the document stays open: use Retry,
then repeat the intended transition. Ctrl/Cmd+S submits a build; the result may be downloaded after
completion. A banner marks results that no longer match the displayed source. Project ZIP export
and Telegram send require a successful save first.

## Dependencies and side effects

Requires auth/local storage, `frontend_i18n.js`, the existing Studio API, and the supporting state
and loader modules. It writes private drafts/job metadata to account-scoped browser storage and
project text/assets to the API. Auth tokens remain in the established auth storage; draft keys do
not include them. The asset preview URL retains the existing authenticated token-query contract.
Exports create short-lived blob URLs. The controller never sends a Telegram message except from
the explicit send button. All UI copy lives in the shared RU/EN locale JSON.

## Maintenance

Preserve reject-on-save-failure, account isolation, filename `textContent`, sanitizer/SRI/CSP,
and manual asset version bumps. Keep job response shapes aligned with `studio_jobs_router.py`.
Use `tests/test_studio_frontend.py` and browser QA for dirty transitions, HTTP 500/retry, reload
recovery, mobile startup, auth return-to, RU/EN, real CDN load order, and keyboard focus. Browser
QA must exercise both Monaco and the fallback editor. Project-wide graph updates are coordinated
after the complete feature set rather than independently by parallel agents.

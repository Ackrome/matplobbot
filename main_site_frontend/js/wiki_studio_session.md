# Studio session state

`studio_session.js` owns the account-scoped local draft journal and serial server-save queue.
It is exposed as `window.MpbStudioSession` and as a CommonJS export for Node tests.

`accountScope(token)` derives a draft namespace from the signed-in JWT subject; it does not
authorize requests. `create({storage, scope, save, onStorageError})` injects storage and transport.
Call `open({projectId, fileId, type, content})` after flushing the previous document, `edit(text)`
on input, and `await flush()` before a transition, build, Telegram send, or ZIP export.
`snapshot()` and `dirty()` expose status. A recovered draft whose base differs from the server
requires `resolveConflict(useDraft)` before saving. Quick snippets remain local drafts.

Example: `const session = MpbStudioSession.create({storage: localStorage, scope: '42', save});`
`session.edit('new text'); await session.flush();`

Dependencies are browser storage, JSON, and a promise-returning save callback. Writes to local
storage contain document contents, never auth tokens. Successful saves remove matching drafts;
edits made during an in-flight save survive. Storage failure reports through the callback and
does not disable editing. Job metadata can use the same account-scoped value helpers.

Keep save failures rejecting, transitions ordered, and account namespaces isolated. Regression
tests cover failures, retries, switching, concurrent edits, and recovery. Do not treat timestamps
as server revision checks or promise cross-device conflict resolution.

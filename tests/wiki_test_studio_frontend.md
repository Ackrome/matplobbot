# Studio frontend regression tests

`test_studio_frontend.py` runs Node against the actual dependency-free Studio session module
and extracts the actual safe-login return-path function. `TestStudioFrontend` verifies rejecting
saves retain drafts, retry saves the original document, concurrent edits are serialized, accounts
are isolated, quick snippets survive reopen, changed server content needs a conflict decision,
storage failures do not destroy editing, and login targets reject cross-origin and loop URLs.

Run `.venv/Scripts/python -m unittest tests.test_studio_frontend -v` from the project root.
Dependencies: Python unittest and Node.js; the test skips when Node is unavailable. Storage and
network are injected in memory, so no API, browser state, credentials, or files are changed.

Keep assertions behavioral. These tests complement rendered browser QA; they do not verify
Monaco, real CDN loading, CSS, assistive technology, or production HTTP services.

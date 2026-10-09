# Curriculum publication CLI tests

`test_publish_curriculum_bundle.py` exercises the standalone helper against an
in-memory `FakeClient`, with temporary synthetic PDF bytes and no production
connections. `PublicationBundleTests` covers bundle/path/hash/schema validation,
official URL and credential transport restrictions, read-only dry runs, backup
ordering, creation/publication and idempotent repeats, preserved group bindings,
cross-document ownership conflicts, publication overwrite refusal, changed local
PDFs, final persisted-state verification, bounded polling and sanitized HTTP errors.
Supplement tests cover child-first input ordering, dry runs before either ID
exists, correct parent foreign-key resolution, unchanged repeat runs, preservation
of root group ownership, rejection of direct child bindings/cohort mismatch,
missing/self/nested/cyclic references, and conflicts with an existing parent ID.

Run from the root:

```sh
.venv/Scripts/python.exe -m unittest tests.test_publish_curriculum_bundle -v
```

Dependencies: Python standard library and the helper under test. Side effects are
limited to temporary files removed by each test. The fake API models persisted
results and records mutation ordering; it intentionally does not replace API/DB
integration tests or a post-deploy smoke test. Keep fixture fields consistent
with the administrator API and add regression cases for any new overwrite path.

# Curriculum document regressions

`test_curriculum_documents.py` tests the official PDF download policy and
assessment extraction without accessing the network or personal timetable data.

## Test components

- `synthetic_pdf(rows, draw_grid=True)` builds a minimal, explicitly synthetic
  ASCII PDF in memory using standard Helvetica. The geometry is processed by
  the real `pdfplumber` parser; no PDF-authoring package is required for tests.
- `CurriculumPdfTests` verifies multiple assessment forms/semesters, provenance,
  explicit ranges, deduplication, parent totals, Russian rotated and merged
  headers, ambiguous numbers, conflicting names, unsupported layouts and invalid
  or blank PDFs, candidate/character/table budgets, and two-digit semester
  ambiguity when the document has no semester workload header.
  Parent practice rows with only blank children are excluded; blank cells do
  not inherit parent grades, and adjacent codes such as `B2.10` are not children
  of `B2.1`.
- `FakeResponse` and `FakeSession` emulate streamed `aiohttp` responses.
- `CurriculumDownloadTests` covers official redirects, external redirect
  rejection before requesting the target, credentials/port/path restrictions,
  HTTP failures, non-PDF responses, timeouts and declared/streamed byte limits.

Run from the project root with UTF-8 enabled:

```powershell
$env:PYTHONUTF8 = '1'
./.venv/Scripts/python.exe -m unittest tests.test_curriculum_documents -v
```

Dependencies are the project runtime (`aiohttp`, `pdfplumber`) and standard
library `unittest`. Tests generate bytes only, perform no HTTP requests, do not
write files and modify no application state. Maintain fixtures as synthetic;
live official documents can change and must not make the unit suite dependent
on university availability. Add a geometry regression before extending parsing
to a different header layout or assessment encoding.

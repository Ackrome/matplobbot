# Official curriculum PDF documents

`curriculum_documents.py` downloads official Financial University PDF uploads and
extracts candidate assessment forms and numbered semesters from ruled tables.
It does not determine which programme, cohort, campus, module or group a plan
belongs to. That association and publication are reviewed in the curriculum
registry service.

## Public interface

- `validate_official_document_url(url) -> str` accepts HTTPS `fa.ru` or
  `www.fa.ru` URLs below `/upload/`. Credentials, nonstandard ports, traversal,
  malformed/control characters and other hosts are rejected. Fragments are
  removed. Rejection raises `CurriculumDocumentError`, a `ValueError` subclass.
- `await fetch_official_document(session, url) -> bytes` uses the caller's
  `aiohttp.ClientSession`, validates every redirect, checks the PDF signature,
  limits downloads to 20 MiB and four requests within a 45-second total budget.
  HTTP errors, timeouts and invalid content raise `CurriculumDocumentError`.
- `parse_curriculum_pdf(content) -> dict` returns `status`, `assessments`,
  `warnings` and `page_count`. Status is `parsed` or `needs_review`. Every
  candidate contains `discipline_code`, `discipline_name`, `semester`, `kind`,
  one-based `page` and a short cell-level `evidence` string. Supported forms are
  `exam`, `pass`, `graded_pass`, `coursework`, `course_project`.

```python
content = await fetch_official_document(session, official_upload_url)
candidate_revision = await asyncio.to_thread(parse_curriculum_pdf, content)
# Persist the PDF hash, URL, retrieval time and review state outside this module.
# Even a parsed result must not create a group binding automatically.
```

## Extraction and safety

The parser depends on `pdfplumber` and its `pdfminer.six` table extraction.
It reads physical table cells, verifies assessment header/data column alignment,
recognizes reversed line order in vertical Russian headers and verifies the
merged code/name header used in FA's wide plans. It does not classify loose
numbers in flattened text. Explicit semester lists/ranges are accepted;
ambiguous cells, conflicting names, missing headers, scans and broken PDFs
produce `needs_review`. Parent rows and named totals/modules are excluded.
The parent hierarchy uses every valid code in validated source tables across
pages, including children whose assessment cells are blank. A practice-section
grade must not become a discipline record or be inherited by blank child rows.
Duplicate assessments are deduplicated, while different semesters and additional
coursework remain separate. The PDF is limited to 100 pages and 200,000
characters per page, one million characters per document, 100 tables per page
and 5,000 assessment candidates. Crossing a document budget returns no records
and an explicit `needs_review` warning rather than a truncated curriculum. A
two-digit semester requires an explicit semester workload header; without one,
the parser cannot distinguish `12` from an undelimited `1,2`. Run synchronous
parsing off the request event loop. These input/output budgets do not replace
process-level memory/CPU limits for PDF decompression and layout analysis.

The module performs network I/O only in the fetch function. Parsing performs no
network calls, writes no files and returns only candidates. A partially parsed
document retains candidates for review but does not claim completeness.
There is no OCR dependency or automatic inference for scanned documents.

## Maintenance and verified samples

`tests/test_curriculum_documents.py` uses explicitly synthetic in-memory PDF
tables and mocked HTTP streams, so tests are offline and contain no student data.
Before supporting another layout, inspect its headers and rendered pages and add
a regression. Never relax ambiguity checks to make a guessed value publishable.

On 2026-10-09, a live download of
`https://www.fa.ru/upload/constructor/e13/mm7ghxp0y1dumv3ons4kyeey1qy0haj1/uchebnyy-plan-PMO_2025-new.pdf`
succeeded and originally produced 91 candidate assessments over three pages.
Source review found two of those records were parent practice sections with
blank child cells. After the hierarchy correction the same source yields 89
explicit discipline assessments. The 91-record count is historical, not the
reviewed publication count. This is evidence for the parser, not a mapping to a 2023 group.
The official catalog's PMO full-time 2023 link,
`https://www.fa.ru/upload/constructor/773/o1glti47zsriv5zhc7qc6agt7g6gou7x/UP.pdf`,
also downloaded successfully but is a two-page scan; it correctly requires
manual review. Live documents are not test fixtures and can change.

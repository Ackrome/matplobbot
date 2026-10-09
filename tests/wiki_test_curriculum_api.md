# test_curriculum_api.py

Supplement API regressions exercise strict optional positive `parent_document_id`,
missing parents, scope mismatch, nested parents, forbidden child group bindings,
parent ID in lists/details, and a separately paginated published supplement.
The public PDF link returns the child's byte-exact snapshot rather than the
base plan. Root deletion unlinks the child while preserving its reviewed PDF.
The source parser is mocked for the deliberately synthetic 40-page metadata;
the existing base-plan test separately exercises real PDF geometry extraction.

Layout coverage verifies optional creation metadata, explicit PUT `/scan-layout`
selection/reset, rejection of unknown profiles or missing/extra fields, and the
same administrator authorization as all other registry mutations.

The end-to-end import test now asserts that HTTP upload returns queued, runs the real bounded background child separately and reads completed detail before publication. It verifies the same source/provenance flow across API schemas, SQLite persistence and the real native PDF parser. Authorization coverage includes cached POST `/reprocess`; OCR itself is never executed inside the request.

The real PDF integration scenario also exercises the HTTP schemas, actual
pdfplumber parser and SQLite persistence together. It uploads a synthetic table,
publishes the returned candidates, binds a group/term, verifies public facts and
the byte-exact PDF snapshot, stages a replacement without changing published
facts, rejects an obsolete publish hash, and deletes the source and binding.

Validates the curriculum HTTP boundary with an isolated FastAPI application and TestClient. Production service functions and rate-limit calls are patched; no upstream HTTP requests or real database changes occur.

`TestCurriculumAPI` verifies administrator authorization on every management route, official-source URL rejection, PDF content type/signature/streaming size limits, unauthenticated cached lookup with rate limiting, query validation, domain conflict/not-found status codes, published snapshot response headers, publication input validation, and the empty successful DELETE response.

Run `.venv/Scripts/python.exe -m unittest tests.test_curriculum_api -v` with UTF-8 enabled. Dependencies are unittest, FastAPI/Starlette, HTTPX and the project's auth/router dependencies. Fixture source URLs/PDF bytes are synthetic and are never downloaded. Keep route coverage synchronized when adding administrative endpoints so a future action cannot omit its administrator dependency.

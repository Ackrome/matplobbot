# curriculum_router.py

PDF uploads and remote refreshes now stage a durable background job and return its current detail (`processing_state`: queued/processing/ready/error). They do not perform PDF or CPU OCR parsing in FastAPI. Administrators poll GET `/curricula/{id}` for completion; GET `/curricula` is metadata-only and omits candidate/published arrays to avoid listing every crop. POST `/curricula/{id}/reprocess` retries the stored PDF without a download (also useful after installing OCR). It retains the same administrator authorization as upload and publication. Publication rejects active processing with 409; OCR metadata/crops are not accepted in the reviewed assessment schema.

Defines the cached public curriculum API and an authenticated administrator workflow for official PDF import, review, publication and group binding. The router is registered under `/api` by `fastapi_stats_app.main`.

## Routes and example workflow

Public routes:

- `GET /api/schedule/curriculum?group_id=162426&discipline=Full%20course%20name&lesson_date=2026-10-09` returns `status`, selected `semester`, all matching `assessments`, source/program metadata, last successful `checked_at`, `stale`, and `review_pending`. The date determines the explicit group-term mapping; this endpoint never calls the university or downloads PDFs.
- `GET /api/schedule/curriculum/documents/{id}/{published_hash}.pdf` returns exactly the current reviewed snapshot. A different or superseded hash returns 404.

All registry routes require `require_admin`:

Creation accepts optional `scan_layout` (`fa_legacy_v1`, `fa_compact_v1`, or null).
It also accepts `parent_document_id` (strict positive integer or null). A parent
must be an existing root curriculum; programme, profile, campus, admission year
and study form must match exactly. Nested supplements or scope mismatches return
422; an absent parent returns 404. List/detail responses include the nullable
parent ID. Direct group binding on a supplement returns 422: its root provides
the verified group calendar. Deleting a root retains its supplementary sources
with null parent IDs and no inferred bindings.

Public course lookup uses each matching reviewed source's own title, source URL,
page, hash and snapshot URL. A BRS page 35 must never point to a two-page base
plan. Multiple source/course identities for the same title return needs_review;
an unpublished supplement cannot produce confirmed facts. Existing public
fields remain compatible; each assessment also exposes `source_document_id`
and `source_sha256`.

`PUT /api/curricula/{id}/scan-layout` accepts `{ "scan_layout": "fa_legacy_v1" }`
or null to restore known-source selection. The field is mandatory for this update
body; unsupported values/extraneous fields return 422. Changing it queues cached
bytes and invalidates old candidates while preserving published facts. No PDF is
downloaded or processed in that HTTP request. Registry/detail responses include
the selected `scan_layout`.

1. `GET /api/curricula` lists documents; `POST /api/curricula` creates `{title,source_url,program,profile,campus,admission_year,study_form}`.
2. `GET /api/curricula/{id}` reads full review details. `POST /{id}/refresh` fetches the source. `PUT /{id}/document` accepts raw `application/pdf` bytes (20 MiB maximum) for a manually obtained official document. `GET /{id}/document` opens its current review PDF.
3. `POST /{id}/publish` accepts `{expected_hash,assessments:[...]}` after an administrator has checked the PDF. Each row requires course code/full title, semester 1–16, exact kind (`exam`, `pass`, `graded_pass`, `coursework`, `course_project`), source page and evidence.
4. `PUT /{id}/groups` accepts `{groups:[{group_id,group_name,terms:[{semester,start_date,end_date}]}]}`. Empty groups remove this plan's bindings.
5. `DELETE /{id}` removes an erroneous/obsolete document and bindings, returning an empty 204 response.

List/detail data include `pending_hash`, `published_hash`, `candidates`, `warnings`, `published_assessments`, `page_count`, `document_url`, `groups`, timestamps and sanitized `last_error`. An import failure returns the retained detail with `last_error=import_failed`; clients must check it. A successful publication clears candidates and changes `status` to `published`.

## Dependencies, side effects and maintenance

Uses FastAPI/Pydantic, the existing administrator dependency and schedule rate-limit configuration, shared API HTTP session, `curriculum_service` and the official URL validator. Both public routes are rate limited. Public PDFs have a PDF content type, `nosniff`, and a content-hash cache key; private review PDFs use `no-store`.

Creation validates an HTTPS university source URL before any persistence. Upload streaming checks bytes as they arrive rather than trusting Content-Length. Normal domain conflicts return 409, missing documents return 404 and invalid review input returns 422. Review code cannot obtain arbitrary upstream response bodies through errors. Tests in `test_curriculum_api.py` cover guards, upload bounds, official-host validation, response contracts and version lookup; service tests cover transactions and matching.

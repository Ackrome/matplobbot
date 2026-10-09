# curriculum_service.py

Stores official curriculum imports separately from administrator-reviewed assessment facts. It uses `CurriculumDocument` and `CurriculumGroup` from `shared_lib.models`, the shared SQLAlchemy session factory, and `curriculum_documents` for bounded official-host PDF downloads and parsing.

## Public operations and use

- `create_curriculum(metadata)`, `list_curricula(id=None)`, `get_curriculum(id)` manage the source registry. Metadata includes the official source URL, edition/title, program, profile, campus, admission year and study form. Optional `parent_document_id` registers a separately reviewed supplementary source. The parent must be a root and all five scope fields must match exactly. Lists and details expose the nullable parent ID.
- `refresh_curriculum(id, session)` retrieves and durably queues a registered PDF. `uploaded_pdf=bytes` stages a manually obtained official PDF. The API returns `processing_state=queued` immediately after storage; parsing happens outside the request. Same source hash and parser/model version skip recognition.
- `process_curriculum_queue()` runs one queued document per scheduler startup/minute tick in the bounded CPU subprocess. `reprocess_curriculum(id)` explicitly retries already stored bytes without downloading, including after installing a missing OCR engine. Detail responses expose queue state, safe processing error, parser version and text/OCR/mixed method; the registry list omits assessment arrays/crops and selected documents must be fetched individually.
- `publish_curriculum(id, expected_hash, assessments)` publishes explicitly reviewed rows. Rows contain `discipline_code`, full `discipline_name`, numbered `semester`, precise assessment `kind`, one-based PDF `page`, and textual `evidence`. Publication rejects a hash that is no longer current, impossible source pages, duplicate identities and conflicting titles for the same discipline code.
- `bind_curriculum_groups(id, groups)` replaces this plan's explicit group mappings. Each group has a RUZ `group_id`, display name, and reviewed semester start/end dates. An empty list removes bindings. A group cannot silently move from another plan. Supplementary documents cannot have direct group bindings, including empty replacement requests; bind the root instead.
- `lookup_curriculum(group_id, discipline, lesson_date)` reads persisted reviewed facts only. It returns all terms for one exact full course title and separately identifies the selected lesson's numbered semester. Ambiguous codes, unconfigured terms and missing mappings return honest unavailable/review states.
- `get_curriculum_pdf(id, published_hash=None)` returns the current review PDF to administrators or an exactly matching published snapshot. Public snapshot bytes remain available during review of a replacement.
- `delete_curriculum(id)` deletes the document, snapshots and bindings atomically. Children are unlinked and preserved as standalone sources without group mappings; both an explicit update and `ON DELETE SET NULL` protect this behavior. In-flight downloads cannot recreate it.
- `set_scan_layout(id, "fa_legacy_v1")` persists explicit scan-column semantics;
  `fa_compact_v1` selects the alternative verified profile and `None` restores
  known-source selection. Creation also accepts optional `scan_layout`. A changed
  profile clears old candidates and queues cached bytes without a download or
  changes to published facts. Repeating the same setting is a no-op.
- `refresh_due_curricula(session)` is the scheduler entry point. An hourly/startup tick considers persisted due dates; documents are fetched every seven days by default, or fourteen when `CURRICULUM_REFRESH_DAYS=14`.

Example: create a plan, import its PDF, inspect/edit the extracted rows, publish with its returned `pending_hash`, and bind a confirmed group with semester dates. Only then does that group's matching course card show confirmed planned assessments.

For additional official BRS or course-program evidence, create another source
with the root's exact scope metadata and `parent_document_id=root_id`. Import,
review and publish that PDF independently. Never copy its page numbers into the
base plan's publication. Public lookup considers the published root and its
direct published children, retaining each assessment's own source title, URL,
`source_document_id`, `source_sha256` and hash-checked PDF snapshot. The selected
semester still comes exclusively from the root's explicit group calendar.
Multiple matching identities `(document_id, discipline_code)`, including the
same title/code repeated in two sources, return `needs_review` rather than a
silent override. An unpublished matching supplement can indicate review is
needed but cannot supply confirmed assessments. A published root is required;
changed supplements preserve their previous reviewed snapshot with stale and
review markers. A defensive scope filter excludes malformed cross-cohort links.

## Side effects and maintenance

Layout changes retain an active child's lease until it exits. Completion checks
captured PDF hash, layout and the processing state; a stale success or failure
cannot overwrite the queued replacement, including a change-and-reset sequence.
Alembic `fb1b2c3d4e5f` adds the nullable profile column. The parser fingerprint
includes scan implementation/configuration, numeric model bytes/metadata and the
selected layout, without importing heavy inference dependencies in the API.
Alembic `fc2c3d4e5f60` adds the nullable indexed supplementary-source self-reference.

Imports make one bounded external download outside the database transaction. A five-minute DB lease prevents overlapping downloads; row locks and hash checks protect publication. A claimed download stays due until success/failure is persisted, so a stopped process is retried after its lease expires rather than postponed a week. Parsing uses a separate 15-minute lease, longer than the subprocess's hard 600-second maximum. Claimers serialize through ordered registry row locks and re-read active leases; a replacement keeps the old child's active slot until it exits, and stale results cannot overwrite newer bytes. Cancellation leaves recoverable work for the next tick after lease expiry.

Successful same-byte rechecks preserve reviewed corrections; parser/model upgrades may rerun extraction but cannot undo human-published corrections for identical bytes. Changed documents become pending candidates; failures retain published facts and snapshots. Download errors use `import_failed`; processing errors use `parse_failed`, `parse_timeout`, `result_limit` or `invalid_pdf`. Missing OCR engines and unsupported table layouts remain review warnings, allowing manual fallback when the PDF page count is valid. Publication is blocked while queued/processing. OCR coordinates/confidence/crops stay in administrator candidate rows and are stripped by assessment validation before publication/public lookups.

There is no inference from group names, cohort digits, shortened course titles, generic RUZ exam flags or a fuzzy match. Two codes with the same title remain ambiguous. Explicit mappings protect different branches/program editions and nonstandard semester calendars. Published results include source provenance and a stale/review marker. PDF blobs are deferred for list and public lookup queries, avoiding large per-card reads.

The source schema is introduced by Alembic `f9f0a1b2c3d4`; `fa0a1b2c3d4e` adds durable processing/version metadata and queues existing stored PDFs. Imports permit PDFs up to 20 MiB and 100 pages. Page-count validation happens in the background; invalid replacements retain the previous published snapshot and cannot be published. Parsing remains conservative; scanned or ambiguous files can be manually reviewed through the admin API. Keep tests in `test_curriculum_service.py`, `test_curriculum_api.py` and `test_curriculum_processing.py` when changing queue, identity, refresh or publication rules. SQLite tests cover actual statements and transaction rollback, but do not simulate PostgreSQL lock contention across processes.

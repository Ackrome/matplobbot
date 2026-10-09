# curriculum_processing.py

Runs CPU curriculum parsing outside the API process. `parse_document_in_worker(pdf_bytes)` starts `python -m shared_lib.services.curriculum_worker`, waits asynchronously and returns its bounded JSON result. `CurriculumProcessingError` contains only a stable API-safe code (`parse_failed`, `parse_timeout`, `result_limit`).

Example: the scheduler service calls `await parse_document_in_worker(source_pdf)` after taking a durable database lease. This module itself has no database or OCR-library imports.

The child receives private temporary input/output files. They are deleted after completion, timeout or cancellation. The environment disables GPU visibility and limits OpenMP/BLAS to one thread. The parent kills the entire process group on Linux, or the child tree using `taskkill` on Windows, so a timed-out Tesseract cannot outlive the job. Output is capped at 8 MiB. Windows development has wall-time/process-tree limits; Linux production additionally applies resource limits in the worker.

`CURRICULUM_PARSE_TIMEOUT_SECONDS` defaults to 300 (30–600); `CURRICULUM_PARSE_MEMORY_MB` defaults to 1536 (512–4096). `current_parser_version(scan_layout=None)` fingerprints parser, layout and numeric backend sources, packaged ONNX weights/metadata, the selected layout and `CURRICULUM_OCR_MODEL_VERSION` (default `tessdata-fast-system`). Hashing these small files needs no ONNX Runtime import, so API images remain lightweight. API and scheduler must carry identical source/assets and the same model tag; change the tag when upgrading external Tesseract language packages.

`validate_scan_layout(value)` accepts `None`, `fa_legacy_v1` and `fa_compact_v1`.
`parse_document_in_worker(pdf_bytes, scan_layout="fa_legacy_v1")` validates that
setting before spawning and passes it as a separate safe CLI argument. Null
allows automatic selection only for source hashes verified by the layout module.

Tests exercise a real text-PDF child, process termination, cancellation, environment limits and cache-key changes. No web request should call this module's processing function directly.

# Resumable Studio compilation

Project jobs select LaTeX, Markdown PDF, or Mermaid PNG from the saved project type.
LaTeX jobs include every saved file and reuse build artifacts. Completed artifacts
are stored only if the current source fingerprint still matches the submitted
snapshot; build cache data is stripped from the public result. Markdown and Mermaid
workers consume the main text file, without packaging auxiliary project assets.

`studio_jobs_router.py` adds asynchronous compilation while preserving the existing synchronous Studio routes.

## API and usage

- `POST /api/studio/jobs` accepts `{"type":"latex","content":"..."}`; Markdown and Mermaid are also supported.
- `POST /api/studio/projects/12/jobs` snapshots the saved files of an owned project.
- Both return HTTP 202 with `job_id`, `status` and `expires_at`.
- `GET /api/studio/jobs/{job_id}` returns queued/running/success/error and the existing compile result shape on completion. A client may poll again after reload or a transient failure.

Every route requires a current account. A foreign or expired job is HTTP 404. Result responses use `Cache-Control: no-store`.

## Dependencies and effects

Uses Celery tasks, the shared Redis client, account authentication, Studio rate limits and SQLAlchemy ownership checks. Owner metadata is stored before publication, and the same UUID identifies the Celery task. Both metadata and results have a 24-hour retention window. Creation fails closed when metadata storage fails. Worker exception objects are not returned to clients. Successful/failed result retrieval records a deduplicated product metric.

## Maintenance

Keep the browser job state contract stable. Do not replace status polling with long blocking result waits. Account deletion must invalidate access to owned job metadata. Heavy rendering still runs in existing workers. Test publication ordering, owner isolation, expired jobs, retryable storage failures, task argument compatibility and successful result retrieval across clients.

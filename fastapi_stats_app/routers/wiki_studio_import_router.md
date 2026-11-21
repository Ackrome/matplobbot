# studio_import_router.py

`POST /api/studio/projects/import/preview` accepts one multipart `file`. It
validates the ZIP and returns a proposed name, project type, main file, paths
and binary flags. The response includes a 10-minute confirmation token tied
to the authenticated owner and the exact archive bytes. Preview does not
create projects or retain files between requests.

`POST /api/studio/projects/import` accepts the same `file` plus `name`,
`project_type`, `main` and `preview_token` form fields. It revalidates bytes and
uses the exported type and main file when the manifest supplies them. A valid
request inserts a new private project and its files atomically. The existing
project, build cache and saved versions do not participate in the import.

Both routes authenticate and rate-limit before reading multipart. The counted
ASGI body stream also caps chunked requests on the direct API origin. The
same-origin nginx location allows 22 MiB to include multipart framing, and the
API/parser independently enforce file and expanded-size limits. Writes reuse
the same account lock and live-project limits as restoring a version. Do not
store or log archive bytes, form tokens or account credentials. The versioned
ZIP comment format lives in `shared_lib/studio_archive.py`.

# studio_versions_router.py

Provides owner-only named versions for Studio projects. It depends on the shared
authentication, rate limiter, PostgreSQL models and existing project ownership
check. Collection and inventory responses use `private, no-store`.

- `GET /api/studio/projects/{project_id}/versions` lists versions newest first.
- `POST /api/studio/projects/{project_id}/versions` with `{"name":"Before review"}` saves a version. The name is unique within its project.
- `GET /api/studio/projects/{project_id}/versions/{version_id}` returns file paths and text/binary/main flags alongside version metadata.
- `POST /api/studio/projects/{project_id}/versions/{version_id}/restore` with `{"name":"Review copy"}` creates a separate project and returns the ordinary project summary.
- `DELETE /api/studio/projects/{project_id}/versions/{version_id}` removes that version and releases its quota.

Snapshots keep the original project name, type, first-class text and binary
contents, path names and main-file flags. Creation and restoration use one SQL
transaction each. Files copy inside PostgreSQL without materializing large
payloads in the API. Project edits lock the project before changing its files.
Writes acquire the account lock before the project lock so multiple projects
share the same version quota consistently. No version edit endpoint exists.

Limits reuse the existing 100-file and 20 MiB compiler envelope per version.
An account can store at most 20 versions or 100 MiB of version file content.
Restore is allowed up to 100 workspace projects and 200 MiB of live file
content. Build caches and jobs belong to the original compilation and do not
transfer. Deleting the source project or account removes its versions. Check
the coordinated project/file lock order before adding another mutation route.

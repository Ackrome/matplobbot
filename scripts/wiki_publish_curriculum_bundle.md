# Publish a reviewed curriculum bundle

`publish_curriculum_bundle.py` is a standalone standard-library CLI for an
explicitly authorized curriculum publication. It does not infer or OCR answers.
The bundle contains reviewed records, exact source PDF hashes and group semester
dates. The default is an authenticated **dry run**: login and registry/detail
reads only. `--apply` is required for changes.

```sh
# STATS_USER and STATS_PASS come from the existing API container environment.
python publish_curriculum_bundle.py --bundle /tmp/reviewed/bundle.json \
  --output /tmp/reviewed/result.json
python publish_curriculum_bundle.py --bundle /tmp/reviewed/bundle.json \
  --output /tmp/reviewed/result.json --apply
```

Default API origin: `http://127.0.0.1:9583`. `--base-url` accepts loopback HTTP or
HTTPS with normal certificate verification; remote plaintext HTTP, URL credentials
and redirects are rejected. System proxies are disabled. Credentials are accepted
only through environment variables. Passwords, bearer tokens and HTTP response
bodies are never printed or included in reports.

## Bundle contract

The top level is `{"version":1,"documents":[...]}`. Each document contains:

- `metadata`: `title`, `source_url`, `program`, `profile`, `campus`,
  `admission_year`, `study_form`, optional `scan_layout` (`fa_legacy_v1`,
  `fa_compact_v1` or null).
- `source_sha256`: lowercase SHA256 of the exact PDF bytes.
- `pdf_file`: relative slash-separated filename contained within the bundle
  directory; absolute paths and symlink escapes are rejected.
- `assessments`: `discipline_code`, `discipline_name`, integer `semester`,
  `kind`, integer `page`, `evidence`. Strip `ocr` and other extraction metadata.
- `groups`: `group_id`, `group_name`, and `terms` with integer `semester`,
  `start_date`, `end_date` in ISO YYYY-MM-DD format.
- Optional `parent_source_url`: official source URL of another **root** document
  in the same bundle. Supporting documents retain their own PDF/hash/page
  evidence and published records; they must have `groups: []`. Their `program`,
  `profile`, `campus`, `admission_year`, and `study_form` must equal the parent's.
  Missing parents, self-links, nested supplements and cycles fail local validation.
  `parent_document_id` is not a bundle metadata field: the helper resolves it from
  the live registry and sends the ID only in the create API request.

Only official HTTPS `fa.ru/upload/` and `www.fa.ru/upload/` sources are accepted.
PDFs are bounded to 20 MiB and checked by signature and SHA before any mutation,
then checked again immediately before use. The server validates actual PDF pages;
the CLI checks returned page counts before publication. All documents and group
conflicts are preflighted before the first batch mutation.

## Main interfaces and behavior

`load_bundle()` validates local input; `AdminClient` implements bounded HTTP;
`read_registry()` and `preflight()` inspect current ownership and publication;
`publish_bundle()` performs the idempotent workflow. `wait_ready()` polls every
five seconds up to `--wait-seconds` (maximum/default 420), printing only changed
processing states. It fails on parser errors or a timeout.

Documents are matched by exact normalized source URL. Existing metadata must
match; an existing published PDF hash or records cannot be replaced. Existing
bindings are merged, not discarded. A requested group already owned by another
document, or conflicting dates/name for an existing group, aborts execution.
Re-running the same completed bundle performs reads without publication writes.
Actual page/hash/records/bindings are verified after mutation.
Roots are created and verified before supplements even if the input lists a child
first. Dry runs allow both parent and child to be new; apply requires the parent
to exist before creating the child. Existing `parent_document_id` must match the
resolved root ID; missing/null is equivalent only for roots. Group ownership stays
on the root, and the public API combines its published supplementary sources.

Before changes, the CLI saves a timestamped `result.json.before-*.json` sidecar
containing existing details and six-field records, excluding OCR image payloads
and credentials. Result JSON is written atomically after every verified document.
Failures preserve the backup and completed-document progress with `status=failed`.
The batch is not an atomic database transaction: partial success must be inspected
and can be resumed by rerunning the same bundle. No rollback or deletion occurs.

The helper rechecks registry ownership before writes, but the current group API
has no optimistic concurrency token. Run it as the sole administrator making
curriculum changes; final GET verification detects lost/unexpected bindings but
cannot provide transaction isolation against a concurrent administrator.

Maintenance: keep validators and allowed fields synchronized with
`curriculum_router.py` and `curriculum_service.py`. This script intentionally needs
neither project imports nor OCR libraries inside the API container. Exit 0 means
validated dry run or complete verified publication; exit 1 means failure.

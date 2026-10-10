# Teacher ratings cache and source access

`teacher_ratings.py` serves the public MyPrepod loyalty aggregate for one exact
Financial University teacher. `teacher_identity(name)` hashes the fixed `fa`
university key and the parser's normalized full name; changing semester-specific
RUZ IDs does not create another association. Initials, multiple teachers and
unsupported names return `unsupported` without database or network work.

`TeacherRatingsService` belongs to the API lifespan and receives its shared
`aiohttp.ClientSession`. `await service.get("Иванов Иван Иванович")` returns
`query_name`, `status`, a minimal nullable profile, `checked_at` and `stale`.
Call `await service.close()` before closing HTTP/DB resources. A caller can supply
`session_factory` for an isolated database; normal use follows `database.get_session`.

The `teacher_rating_cache` table persists the profile URL/name/department,
native 0–100 loyalty percentage, nullable vote/review counts, and matching
provenance. It never stores review bodies. Completed matches and negative results
are fresh for 24 hours. Stale completed data returns immediately while a refresh
runs; failure preserves that data and its original check time, marks it stale,
and delays another attempt for five minutes. An initial failure has no invented
successful retrieval time. Missing statistics remain null, and zero votes cannot
be presented as a zero-percent rating.

Refresh tasks coalesce locally, with at most 32 pending tasks per API process.
Database leases coalesce across processes and expire after 60 seconds. Publishing
requires the original lease token, so an expired worker cannot overwrite a newer
result. The initial request waits at most 22 seconds; source work has a 20-second
budget. The frontend request deadline must exceed the initial backend wait.

Only public MyPrepod HTML URLs accepted by `teacher_rating_source` are fetched.
Search uses the observed university catalogue `q` query. Exact candidates require
a complete filtered search, then exact name/university/profile verification.
Completion requires a stable source result count and distinct validated profile
cards covering that count across all pages. Skipped or repeated cards and changing
counts cannot establish a unique match or a not-found result.
Redirects cannot change the query, page or numeric teacher profile identity.
Bounds: three catalogue pages, ten total HTTP requests, two redirects per request,
one transient retry, four seconds per HTTP request and 2 MiB uncompressed HTML.
Compressed responses are rejected and the HTTP client does not decompress them.
Each API process permits two concurrent HTTP requests with starts at least one
second apart; capacity scales with the explicitly configured API process count.
The route additionally applies the existing Redis-backed per-client limiter.

Outbound requests use `get_global_http_proxy_url()` and the shared session with
explicit timeout/redirect/encoding options. This module does not fetch `/api/`,
take arbitrary user URLs, vote, log lecturer queries, or send Telegram messages.
Maintenance: keep the pure parser's identity checks and service pagination bounds
aligned; preserve the real cache/migration and HTML-boundary tests when changing
TTL, lease, or transport behavior.

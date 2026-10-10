# Public teacher ratings endpoint

`teacher_ratings_router.py` exposes
`GET /api/schedule/teacher-ratings?name=<full name>`. It is public and uses the
existing `RATE_LIMIT_SCHEDULE_SEARCH` settings under the `teacher_ratings` scope.
Names must be nonempty and at most 200 characters; unsupported initials or compound
teacher names return the service's explicit `unsupported` outcome.

`get_teacher_rating` obtains the lifespan-owned service through
`get_teacher_ratings_service`, applies the limiter before lookup, and validates
the result with `TeacherRatingResponse` / `TeacherRatingProfileResponse`.

Example response:

```json
{"query_name":"Иванов Иван Иванович","status":"not_found","profile":null,"checked_at":"2026-10-10T12:00:00Z","stale":false}
```

Statuses are `matched`, `not_found`, `ambiguous`, `unsupported`, and `unavailable`.
A matched profile contains `name`, source `url`, nullable `department`, nullable
`rating_percent`, `vote_count` and `review_count`. These are loyalty statistics,
not a teaching-quality or pass-probability score. `checked_at` is the last valid
source check in UTC, or null before a valid check. Stale matched data remains
`matched` with `stale=true`. Source failures are domain outcomes; validation and
rate-limit errors retain normal HTTP 422/429 handling.

Dependencies are FastAPI/Pydantic, the existing request limiter and
`TeacherRatingsService`. The route can trigger bounded source refresh/cache writes
through that service. It exposes no arbitrary URL, RUZ-ID lookup, or review text.
Maintain the frontend's independent per-teacher request lifecycle and a timeout
longer than the backend's 22-second first lookup wait.

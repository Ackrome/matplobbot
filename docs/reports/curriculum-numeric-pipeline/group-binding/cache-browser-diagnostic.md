# Full-cache browser diagnostic — 2026-10-10

The automated browser displayed a loading error in the **Дисциплина** tab for
**Алгебра и геометрия**, ПМ25-1 (RUZ group 164554). This was investigated separately
from the curriculum group-context fix.

Both public hosts return HTTP 200 for `/api/schedule/cache/group/164554`, with
386 lessons, a correct string entity ID, valid JSON and a complete 1,420,766-byte
body. Requests took approximately 0.6 seconds. The API logs also show successful
200 responses for both original UI attempts. The ПМ23-1 control request returns
473 lessons and a larger 1,786,391-byte body in approximately 1 second.

The downloaded production `schedule.js` and `lesson_details.js` transformations
were replayed against the actual ПМ25-1 response in Node VM. Module preparation,
lesson normalization and related-lesson selection finish without an exception,
yielding **43 Algebra lessons**. No user contact details or full raw timetable
are retained in this report.

The root agent separately navigated CUA directly to the ПМ25-1 cache endpoint;
the browser returned **`net::ERR_BLOCKED_BY_CLIENT`**. The service's public HTTP
response and client data transformations are verified; successful rendering of
this response in the restricted automated browser is not. No application bug
was reproduced, so no application patch was made for this diagnostic.

Exact counts, timings, response metadata and production asset hashes are in
[`cache-browser-diagnostic.json`](cache-browser-diagnostic.json). These checks
did not inspect hidden browser state or change production data.

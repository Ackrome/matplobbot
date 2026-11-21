# Reviewed curriculum aliases

`curriculum_aliases.json` contains source-reviewed links from an exact RUZ
discipline name to a published curriculum record. The curriculum service applies
an alias after an exact title lookup, and only when the group, RUZ plan ID,
discipline ID, and the published PDF SHA-256 all match. The same registry is used
for lesson cards and scheduled assessment dates.

Each entry has `group_id`, `plan_id`, `discipline_id`, `ruz_title`,
`canonical_title`, `source_sha256`, and `evidence`. Use the canonical title as
published and reference the plan page and confirmed RUZ association in
`evidence`. Add entries through source review and deploy with the application.
Recheck an existing link before changing its PDF hash or any RUZ identifier.
Both files are maintained with the Python package, and the runtime registry is
cached in process memory. The initial registry has no approved aliases.

# Public MyPrepod source parser

`teacher_rating_source.py` parses public Financial University catalogue and teacher
profile HTML. It is pure standard-library code: no HTTP requests, database writes,
JavaScript execution, dependency additions or review-text storage.

## Verified source contract

On 2026-10-10, the public catalogue at
<https://myprepod.ru/universiteti/fa/prepodavateli> exposed a `data-tutor-catalog`
element. Its JSON `data-config` contains `baseUrl`, `found` and `state.q`; the public
JavaScript constructs ordinary HTML requests with `?q=<full name>` and `page`.
Teacher cards are profile anchors with a full-name `h3` and a matching title.
Pagination uses ordinary anchors and `link rel="next"`.

The example profile
<https://myprepod.ru/fa/cupreeva-alena-nikolaevna-15271> uses an `Organization`
JSON-LD node for the teacher, with the exact profile URL, teacher full name and
`parentOrganization` of type `CollegeOrUniversity`. The parser supports this
observed representation and a `Person` representation with the same identity
evidence. It requires the university's exact catalogue URL and known university
name. A nearby department aggregate or a review author's `Person` node cannot
supply the rating.

`robots.txt` allowed these public routes at that check and disallowed `/api/` and
`/legacy-tutor-redirect/`. Neither route is supported here. Recheck access rules
and actual HTML when maintaining the integration; public source structure can
change.

## Public helpers

- `display_teacher_name(value)` replaces underscores and collapses whitespace,
  retaining original spelling for display and search.
- `normalize_teacher_name(value)` additionally case-folds and maps `ё` to `е` for
  exact comparisons. It never reorders names or expands initials.
- `is_full_teacher_name(value)` accepts one three-part Cyrillic full name, with
  optional hyphens inside a part. Initials, two-part names, mixed teacher lists
  and unsupported scripts must remain an explicit unsupported service result.
- `build_catalogue_url(name, page=1)` builds the fixed public GET search URL.
- `validate_source_url(url, profile_only=False)` rejects credentials, ports,
  other hosts/schemes, encoded paths, redirects/API paths and unknown queries.
  The HTTP caller must validate every redirect before following it and also
  preserve the original query or profile identity; this allowlist alone does not
  prove a redirect remains the same teacher.
- `parse_catalogue(html, expected_name, source_url=None)` returns a frozen
  `CatalogueResult`: exact `TeacherCandidate(name, url)` objects, later `next_urls`,
  all validated card `observed_urls` (including nonmatching full names),
  `total_found`, `search_complete`, and `ambiguous`. Duplicate links to the same
  profile are deduplicated; distinct profiles sharing the full name are ambiguous.
  The caller must traverse all required pages within its budget before accepting
  a unique match or absence. A truncated catalogue is never a negative match.
  Across pages, the service must require a stable `total_found`, no repeated card
  URLs between pages, and exactly that many distinct `observed_urls`; reaching a
  last-page link alone cannot prove a middle page was not skipped.
- `parse_profile(html, expected_name, source_url)` returns a frozen
  `TeacherRatingProfile(name, url, department, rating_percent, vote_count,
  review_count)` after identity checks. `SourceParseError` means unsupported or
  inconsistent source data; `AmbiguousTeacherError` means conflicting identities
  or aggregates; `UnsafeSourceUrl` means an invalid source URL.

```python
from shared_lib.services.teacher_rating_source import build_catalogue_url, parse_catalogue, parse_profile

name = "Чупреева Алёна Николаевна"
url = build_catalogue_url(name)
# An owning service supplies bounded, validated HTML; this module does no I/O.
catalogue = parse_catalogue(catalogue_html, name, url)
if catalogue.search_complete and not catalogue.ambiguous and len(catalogue.candidates) == 1:
    profile = parse_profile(profile_html, name, catalogue.candidates[0].url)
```

## Bounds and maintenance

Input HTML is limited to 2 MiB; JSON schema traversal to 2,048 root/graph nodes.
Duplicate JSON keys and non-finite values fail closed. Ratings retain the source's
native 0–100 loyalty scale and require explicit `bestRating=100`, `worstRating=0`.
They are not teaching-quality or exam-outcome predictions. Counts are nonnegative
integers up to 2,147,483,647. Missing values stay `None`; zero votes suppress the
rating while a zero rating with votes remains valid. No average is synthesized.

Only the aggregate, department and identity are returned. Review bodies are never
returned or persisted by this parser. Keep realistic fixtures in
`tests/test_teacher_rating_source.py`, including wrong-university profiles,
same-name ambiguity, pagination changes and malicious links. Revalidate one
public catalogue/profile pair after source-structure changes without crawling
unrelated profiles or using disallowed API endpoints.

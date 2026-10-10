# MyPrepod source parsing regressions

`test_teacher_rating_source.py` contains deterministic `unittest` regressions for
the pure MyPrepod public HTML parser. It performs no network, filesystem or
database operations and requires no third-party test fixtures or dependencies.

The `teacher`, `structured`, `card` and `catalogue` helpers construct minimal
realistic HTML/JSON-LD fixtures using the source structure observed on 2026-10-10.
Fixtures retain factual aggregate and identity structure without copying reviews.

The test classes cover:

- exact Cyrillic full-name normalization, supported hyphenated parts, rejected
  initials/compound names, and the observed public `q`/`page` URL contract;
- URL allowlisting against credentials, alternate hosts, API/redirect routes,
  path encoding, query injection and invalid pagination;
- catalogue ambiguity, same-profile deduplication, conflicting identity, wrong
  filters, missing schema, incomplete pagination and changed search queries;
- all validated observed card URLs, allowing the service to detect missing middle
  pages, repeated cards and incomplete total-result coverage;
- actual `Organization` teacher JSON-LD and equivalent `Person` graph nodes,
  nearby department aggregates and review-author isolation;
- wrong universities, profile identity changes, duplicate conflicting data,
  invalid scales/counts, bounded input, missing values and valid zero ratings.

Run from the repository root:

```powershell
.venv/Scripts/python.exe -X utf8 -m unittest tests.test_teacher_rating_source -v
```

When MyPrepod changes its public HTML, verify it with bounded public reads first,
then update both parser and fixtures. Do not loosen identity checks to make a
fixture pass or turn missing/invalid information into a zero score. HTTP retry,
redirect execution, cache persistence and service-level pagination budgets belong
to the owning teacher-ratings service tests, not this module.

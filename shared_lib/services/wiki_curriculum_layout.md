# Declared curriculum table layouts

`curriculum_layout.py` maps physical columns to five assessment forms without
recognizing printed headers or discipline indices. `TableLayout` is immutable;
`resolve_layout(source_sha256, requested)` chooses an explicit registered profile
or an exact, visually checked source hash. `validate_grid(xs, ys, shape, layout)`
checks column proportions and the geometric header boundary before extraction.

Example: `resolve_layout(digest, "fa_legacy_v1")` selects exam/pass/coursework/
course-project at columns 4/5/6/7 and graded pass at 9 (zero-based). The compact
layout instead uses graded pass/coursework/project at 6/7/8. A known source cannot
be explicitly assigned its conflicting profile. Admission year alone is not a
layout detector. Similar grids cannot establish column semantics without a
declaration; unknown sources are rejected until their template is specified.

No heavy dependencies, network calls or file writes. Maintenance: inspect actual
source headers when registering a new template, version the layout rules, test
missing/shifted grid lines and preserve previously registered interpretations.
The runtime itself never reads headers, index text, GT or assessment answers.

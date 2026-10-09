# FA Applied Machine Learning 2023 scan ground truth

The current production pipeline recognizes names and control-cell sequences
only. Printed indices retained in these historical audit annotations are not
inference inputs and are excluded from current end-to-end matching.

This development/audit fixture covers **all 91 physical body rows on both pages**
of the 2023–2027 full-time curriculum, limited to the scope requested by the user:
the printed discipline index, title, and five forms of assessment. Hours, credits,
and workload columns are excluded. There are 66 discipline rows, 23 section rows,
2 summary rows, and 455 assessment cells, including empty cells. The discipline
rows contain 79 explicit `(row, assessment kind, semester)` facts.

- Official PDF: https://www.fa.ru/upload/constructor/773/o1glti47zsriv5zhc7qc6agt7g6gou7x/UP.pdf
- SHA256: `73d6fa541ce75445d21d3e6ed810ee532954959056f6d9cf314e0f84fcd94bf3`
- PDF size: 2,735,776 bytes; two scanned pages.
- Annotation date: 2026-10-09.
- Method: two agents transcribed separate original rendered pages visually,
  without consulting the OCR candidates; the root agent independently inspected
  all original row chunks and checked both resulting transcriptions. This is
  agent-created visual GT, not an externally certified university dataset.
- GT is frozen before scoring the OCR experiments. It is evaluation data, never
  a recognition dictionary, grid template, or correction source.

## Files and interpretation

`fa_pmo_2023_page1_gt.json` contains 54 rows (43 disciplines, 11 sections);
`fa_pmo_2023_page2_gt.json` contains 37 (23 disciplines, 12 sections, 2 summaries).
`row_id` identifies physical position independently of the printed index, which
is not unique in this source. `bbox` is normalized to the **original page**, before
deskew. `render_scale` documents annotation rendering, not an OCR requirement.

`controls` retains each printed cell as a string. `""` is a visually verified
empty cell, not an unknown value. `semesters` records explicit interpreted semester
numbers; counts in section/summary rows are not semesters. Section-scoped values
remain on the section and are not copied into blank child discipline cells.
Line-wrapped names are joined with spaces; printed spelling and indices are kept.
The five keys are `exam`, `pass`, `graded_pass`, `coursework`, `course_project`.
The neighbouring «Контрольные работы» column is intentionally excluded.

Assess OCR cell transcription on every row; assess discipline facts separately.
Do not let hundreds of empty cells hide poor recall on the nonempty cells.
Report incorrect additions in blank cells, missed facts, row/header failures,
and name/code errors independently. Unknown recognition and empty recognition
must have different representations in predictions.

## Source-specific traps

- `p1_r009` («Иностранный язык в профессиональной сфере») and `p1_r034`
  («Эконометрика») both print `Б.1.2.1.6`. Do not silently correct the source index
  or merge these two disciplines.
- `p1_r008` has passes `1,2,3`; `p1_r024` has passes `1,2,3,4`.
- `p1_r023` («Машинное обучение») has **course project 4**, not coursework.
- `p1_r046` has both pass 6 and coursework 6.
- `p2_r023` and `p2_r025` contain section-scoped graded passes `8` and `8,8`.
  Child practice cells are blank. A footer says practices have graded passes;
  that contextual statement is not a printed child-cell value.
- `p2_r029` has passes `2,4,6`. `p2_r030` has a small scan artefact in an otherwise
  empty exam cell. The state-exam title in `p2_r031` does not fill that cell.
- `p2_r034` contains a count of one; its child `p2_r035` has pass semester 2.
- `p2_r037` has graded pass 5, which baseline OCR missed.

These two pages form a development set. Thresholds chosen on them have no
independent test-set guarantee; validate another curriculum before enabling
automatic matching/publication.

`fa_pmo_2023_ruz_names_2026-10-09.json` is an independent name vocabulary from
the public RUZ group `162426` (ПМ23-1), requested for 2026-08-25 through 2027-01-31.
It contains 21 unique course names from 473 timetable occurrences, with the
request URL and retrieval date. It is a partial semester vocabulary, not the
complete curriculum and not proof that renamed courses are equivalent. The
benchmark uses it only for name-matching experiments after raw OCR. A GT-derived
oracle dictionary, if evaluated, must be labeled as an upper bound with leakage
and excluded from deployment recommendations.

## Independent native-text 2025 annotations

`fa_pmo_2025_page{1,2}_native_gt.json` covers 102 physical rows, including 76
disciplines, 24 sections and 2 summaries; 510 control cells and 89 explicit
discipline facts. Source SHA256:
`26aa4732da0efe213f5e2426ce63c85c04ab15a854c1542c4264d5d4c9239b86`.
The source has three PDF pages; the third has no annotated discipline table.

`scripts/curriculum_vector_gt.py` extracted answers from native PDF vectors/text,
independently of raster OCR and the 2023 answers. Header meanings were visually
checked. Header/index extraction here is an evaluation-only activity. The
production pipeline never reads these files or recognizes those fields.

Rasterized 2025 pages test another column layout and wrapped numeric cells.
They are not independent noisy scans, and pipeline geometry/wrapping rules were
developed using them. The numeric model remained frozen and synthetic-only.
See [the complete report](../../../docs/reports/curriculum-numeric-pipeline/README.md).

# Evidence for the ПМ23 / ПМ25 group bindings

Verified on 2026-10-09 against public Financial University sources. This is a
read-only evidence snapshot; it does not itself register or publish data.

## Current groups

The complete [RUZ group dictionary](https://ruz.fa.ru/api/dictionary/groups)
contained 4,060 records. Exactly eleven group names matched
`^ПМ(23|25)-[0-9]+$`:

| Cohort | Group | RUZ ID | Current numbered semester |
|---|---|---:|---:|
| 2023 | ПМ23-1 | 162426 | 7 |
| 2023 | ПМ23-2 | 162428 | 7 |
| 2023 | ПМ23-3 | 162430 | 7 |
| 2023 | ПМ23-4 | 162432 | 7 |
| 2023 | ПМ23-5 | 162434 | 7 |
| 2025 | ПМ25-1 | 164554 | 3 |
| 2025 | ПМ25-2 | 164555 | 3 |
| 2025 | ПМ25-3 | 164556 | 3 |
| 2025 | ПМ25-4 | 164557 | 3 |
| 2025 | ПМ25-5 | 164558 | 3 |
| 2025 | ПМ25-6 | 164559 | 3 |

Every group has faculty ID 6, full-time study, active schedule, and course 4
(2023 cohort) or 2 (2025 cohort). The
[faculty dictionary](https://ruz.fa.ru/api/dictionary/faculties) identifies faculty
6 as the Faculty of Information Technology and Big Data Analysis in the Moscow
campus. RUZ's speciality and specialization fields are empty: those fields alone
cannot prove the program/profile.

The returned lessons independently name their source schedules
`*7 семестр - ПМ23-1-5 - 4 курс` and
`*3 семестр - ПМ25-1-6 - 2 курс`. Their `disciplineinplan` values are 3860 and 6088,
matching the relevant curriculum footer identifiers. All five 2023 groups have
the same seventeen current discipline titles; differences in lesson counts do
not imply different study plans. The 2025 groups share the same core titles.
Some foreign-language lessons are scheduled through another faculty's stream;
that does not change the student's curriculum affiliation.

Composite search entries 165524 and 165623 are not individual groups and are
excluded. Historical official publications mention ПМ23-6 and ПМ25-7, but neither
has a current individual record in the complete dictionary or exact search.
No ID is guessed for these historical labels.

## Official program and revisions

The current [official educational-program catalog](https://www.fa.ru/sveden/education/edupr/)
has one Moscow full-time row for 01.03.02, Applied Mathematics and Informatics,
program and profile “Прикладное машинное обучение”, with year-specific editions.
Its extracted row is preserved in `catalog-program-row.html` (relative links
refer to `https://www.fa.ru`).

The 2023 catalog plan is the same reviewed scan as the numeric pipeline report.
The 2025 catalog currently links a signed two-page scan, SHA256
`4de019ce8ffd0ec18abfad63a199e2417b8bf55b509ab97e55ac25d07f65556f`,
with footer ID 006088. This is different from the native 2025 “new” PDF used in
the benchmark, SHA256
`26aa4732da0efe213f5e2426ce63c85c04ab15a854c1542c4264d5d4c9239b86`.
The University's [Center for Digital Transformation and Artificial Intelligence](https://www.fa.ru/university/structure/scientific-educational-departments/itabd/centrai/)
explicitly publishes that “new” PDF as its study plan. Both are official sources;
the comparison/publication step must record which edition supplied each fact,
not silently substitute documents because the admission year agrees.

The current 2025 timetable includes “Математика искусственного интеллекта”. The
signed catalog scan leaves the individual facultative-discipline list to local
acts/course working programs, while the “new” native PDF explicitly lists these
facultatives. This explains why timetable-name coverage alone is insufficient to
select every assessment from either edition.

## Semester dates

Both linked cohort calendars were downloaded and visually inspected:

- [2023–2027 full-time calendar](https://www.fa.ru/upload/constructor/097/bz23oq9v6en1grnexho4qvh7119g6tnf/KUG.pdf), approved 2023-01-31.
- [2025–2029 full-time calendar](https://www.fa.ru/upload/constructor/908/3504j6nh3idpc6elldfzlpvl9klpboe2/KUG_PMiI_25_och.pdf), approved 2025-01-31.

The printed columns specify autumn teaching from September 1 through December
28, assessment/public holidays from December 29 through January 11, assessment
through January 25, then vacation January 26 through February 1. The next term
starts February 2. These support inclusive current-term bounds **2026-09-01 to
2027-01-25** for numbered semester 7 / 3, respectively. The bounds come from the
cohort calendars, not from the earliest/latest cached lesson. A separate annual
Moscow calendar overriding these dates has **not** been independently verified.

For courses 1–3, the printed spring assessment period ends June 28, with vacation
starting June 29. For course 4, practice occupies February 2–May 17, followed by a
break and state final certification May 25–July 5. Do not interpret this as a
regular taught eighth semester or invent examination dates from it.

The page renders `calendar2023-1.png` and `calendar2025-1.png` preserve the visual
basis for the date reading. Hashes, source URLs, exact current groups, and slim
lesson summaries are in `evidence.json`; individual lecturers/contact details
are intentionally absent from this retained snapshot.

The separate [full-cache browser diagnostic](cache-browser-diagnostic.md) records
the successful public API and JavaScript replay checks for ПМ25-1, and the
automated browser's `ERR_BLOCKED_BY_CLIENT` restriction during visual validation.

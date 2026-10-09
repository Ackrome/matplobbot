# Coverage of the current timetable titles

`coverage.json` compares every unique current title across all eleven groups with
`publish-2023.json` / `publish-2025.json`. It uses the actual API's whitespace and
case normalization only. It records expected API statuses, publication hashes,
all matched terms and current-term controls. These are preflight expectations,
not a claim that live API verification already passed.

| Cohort | Current titles | Found in base publication | Controls in current numbered semester |
|---|---:|---:|---:|
| ПМ23, semester 7 | 17 | 14 | 14 |
| ПМ25, semester 3 | 13 | 11 | 9 |

There are no unresolved case/whitespace differences among the matched titles.
“Основы деловой и публичной коммуникации” matches exactly and has a pass in
semester 7. “Учебно-научный семинар” and “Элективные дисциплины по физической
культуре и спорту” match the 2025 publication, but their control is in other
semesters. The API may correctly return `confirmed` for their title while the
card has no current-semester assessment.

## Why the missing titles cannot inherit another result

“Военная подготовка” belongs to RUZ plan 6142 in both cohorts. It is not a proven
alias for the ordinary curriculum's “Основы военной подготовки”. It remains
unconfirmed.

The generic “Практическая подготовка” in ПМ25-1 does not identify which named
practice/year it represents. It remains unconfirmed rather than inheriting the
first practice row.

“Машинное обучение на графах” and “Технологии и алгоритмы анализа сетевых моделей”
belong to RUZ plan 3860 for ПМ23, not 6142. Neither is a row in the reviewed 2023
curriculum. Inspection of all 58 DOCX programs in its official RPD archive found
neither exact title. The separate course “Машинное обучение в семантическом и
сетевом анализе” is not a justified alias. Newer cohorts/master plans cannot
supply the missing controls merely because a subject title matches.

## Additional current official evidence found

The live [AI department bachelor page](https://www.fa.ru/university/structure/scientific-educational-departments/itabd/ai/study/bachelor/)
now links a [grading document for autumn 2026/2027](https://www.fa.ru/upload/constructor/62f/cvigxrmcv4janm7wj3k351mqpl9o1lxd/-Obshchiy-fayl-BRS-1-sem-26_27.pdf).
Its page 13 explicitly specifies a pass for the graph-learning course; the title
omits “на”, and its author Кузина О.Н. is a lecturer in the current ПМ23
schedule. Page 35 explicitly specifies a pass for the network-model algorithms
course, with exact title and lecturer Карпухин А.И. Both pages were visually
checked and retained as PNG evidence.

These two supplemental facts are saved in `supplemental-brs-evidence.json` with
their own source URL/hash. The numbered semester 7 is established by RUZ; the
source's wording “first semester studying the discipline” must not be parsed as
numbered semester 1. They are not yet part of the base `coverage.json` expectation
and must not be presented as pages of the two-page curriculum PDF. Integration
must preserve the separate document provenance.

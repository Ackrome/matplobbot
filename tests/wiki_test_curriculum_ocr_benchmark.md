# OCR benchmark metric tests

`test_curriculum_ocr_benchmark.py` verifies the offline benchmark's evaluation
protocol without invoking OCR or downloading models. `BenchmarkMetricTests`
covers the strict ANLS boundary, lexical-match margins, independent-family
consensus, abstention, geometry-only alignment, omitted rows, false-positive
blank cells, missing headers, strict code/title identity, existing candidate-name
cleanup and section totals that must not become semester facts.

Run `./.venv/Scripts/python.exe -m unittest tests.test_curriculum_ocr_benchmark`.
The small `truth_row` and `predicted` helpers construct synthetic annotations and
predictions. Dependencies are unittest and the benchmark's pure evaluation
functions (semester parsing imports the existing curriculum parser).

Tests have no filesystem/network side effects. Maintain these protocol invariants
when adding OCR backends: repeated configurations of one model cannot manufacture
a majority, GT labels cannot align rows, and an abstention is not a correct blank.

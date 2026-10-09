# Curriculum raster helpers and legacy OCR benchmark

`curriculum_ocr.parse_scanned_curriculum` now delegates to the
[name OCR + numeric CNN pipeline](wiki_curriculum_pipeline.md), which never reads
printed indices or headers. The geometry/Tesseract helpers remain shared.
The documentation below describes `parse_scanned_curriculum_legacy`, retained
for reproducible historical comparisons, not production fallback.

The legacy implementation extracts **review candidates**, never automatically approved
facts, from Financial University PDF scans containing a ruled assessment table.
The import worker calls it only for selected scan pages; ordinary text PDFs keep
the native parser. No GPU, cloud OCR, network call or persistent model process is
required.

## Interface and example

```python
from shared_lib.services.curriculum_ocr import parse_scanned_curriculum_legacy

result = parse_scanned_curriculum_legacy(pdf_bytes, page_numbers=[1, 2])
assert result["status"] == "needs_review"
# Persist the returned candidate revision and show it in the admin review UI.
# This does not bind the curriculum to a programme, cohort or student group.
```

`page_numbers` is an optional one-based subset for mixed text/scanned documents.
The result contains `assessments`, `warnings`, PDF `page_count`, `method="ocr"`
and an `engine_version` containing the parser version, installed Tesseract
version and configured model version. Every assessment retains discipline code,
name, numbered semester, precise assessment kind, source page and raw OCR
evidence. Its `ocr` object adds minimum word confidence, normalized row `bbox`,
`page_rotation`, `deskew_degrees`, `review_required=true` and a PNG row crop in
`crop_png_base64`. Confidence is an engine diagnostic, not correctness probability.
Bounding boxes refer to the rendered, deskewed page; the crop is the direct visual
evidence. Preview crops may be omitted when the total size budget is reached.

`OcrUnavailable` is an internal operational failure: missing binary/language data,
timeout or resource limit. The public function converts failures into explicit
review warnings, with stable `ocr_unavailable:` and `ocr_timeout:` prefixes for
the admin's localized help.

## Geometry and recognition

- PDFium renders one page at a time. OpenCV estimates small page skew using
  long horizontal rules, then detects horizontal and vertical lines.
- The merged discipline-name header must be readable. Each rotated control
  header is recognized independently. Column order is never used to guess
  whether a number denotes an exam, pass, graded pass, coursework or project.
- The left identity columns and physical horizontal rules supply cell boundaries.
  Padded column strips batch the OCR work while retaining a mapping back to each
  source row, including wrapped course titles and empty assessment cells.
- Tesseract TSV words use literal quotation marks, not CSV-escaped fields.
  Read them with `csv.QUOTE_NONE`; default CSV quoting can consume subsequent
  records when a title begins with a quoted word. The 2023 plan exposed this
  in module headings such as `Модуль "Анализ данных"`. Parser revision
  `fa-grid-ocr-2` repairs the transport parsing without changing recognition
  models. The worker cache version is likewise `curriculum-text-1-ocr-2`, so
  existing sources can be reprocessed while reviewed publications are preserved.
- Semester lists/ranges use the conservative native parser. Undelimited `78` or
  `123` are unresolved. Parent/module totals are discarded. Joined discipline
  codes are rejected. Blank cells with hallucinated OCR digits are rejected by
  checking actual source ink.
- A stray trailing standalone border glyph such as `=` is removed from the
  candidate title; the raw OCR title remains in `evidence`. Other OCR errors
  require administrator correction. Publication and group binding remain separate.

The supported baseline is a landscape, legible ruled FA table with a readable
header on each page. Unruled tables, badly damaged lines, sideways embedded scans,
nonstandard headers and ambiguous cells require review/manual entry. Missing rows
must not be interpreted as absence of an assessment. Crops and the complete PDF
remain necessary for validating omissions as well as extracted values.

## Dependencies, budgets and side effects

Dependencies are `opencv-python-headless`, NumPy, Pillow, `pypdfium2`, Tesseract 5
CLI and `rus+eng` language data. Set `CURRICULUM_TESSERACT_CMD` for a nonstandard
binary (`TESSERACT_CMD` is a fallback), `TESSDATA_PREFIX` for a language-data
directory, and `CURRICULUM_OCR_MODEL_VERSION` when changing installed models.
Tesseract defaults to a binary on PATH. No shell command interpolation is used.

Limits: 20 MiB PDF, eight selected scan pages, 24 million rendered pixels per
page/strip, 6000-pixel render edge, 200 physical rows per page, 1000 records,
240-second document budget and 20 seconds per OCR invocation. A bounded outer
worker must still enforce process memory and wall time: native PDF/image parsing
can fail before cooperative checks. Record budget failures clear partial results.

Tesseract uses `OMP_THREAD_LIMIT=1`; OpenCV uses one thread in the worker. Each
invocation writes a PNG in a temporary directory and deletes it on normal exit.
Crop PNGs are capped at 20 KiB each and four MiB total base64 in a result. Inputs
and candidates are otherwise kept in memory. The module does not mutate the DB.

## Validation and maintenance

Run `python -m unittest tests.test_curriculum_ocr -v` from the root virtualenv.
These tests use synthetic raster geometry and mocked OCR words, with no network
or Tesseract requirement. Set `CURRICULUM_OCR_TEST_PDF` for an optional local
real-engine integration check. Inspect actual rendered source crops before
loosening recognition rules; add regressions for observed false positives.

On 2026-10-09 the actual two-page 2023 Applied Machine Learning scan yielded
review candidates in about nine seconds on the development computer using
Tesseract 5.5.3 and tessdata_fast 4.1.0. This is not a server performance guarantee.
The source row crops confirmed semester 7 exam candidates for `Семантические
технологии` and `Электронные деньги`, and a semester 7 pass candidate for
`Программирование для встраиваемых систем`. Some other rows/codes remain
unresolved or need correction. This is extraction evidence, not a confirmed
association of the document with a particular user's group.

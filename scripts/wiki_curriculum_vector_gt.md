# Native-PDF curriculum evaluation reference

`curriculum_vector_gt.py` creates an independent evaluation reference from a
Financial University PDF with real text and ruled vector cells. It consumes no
OCR predictions, no scan GT, no course dictionary and no expected semester map.
Its purpose is to check a frozen OCR/fusion algorithm on another clean layout;
rasterizing native text is **not** evidence of noisy-scan generalization.

`extract_native_gt(pdf_path)` finds the largest ruled table per native-text page,
identifies its five assessment headers (including rotated text), and preserves
every physical body row. It emits original-page normalized cell boxes, native
column indices, exact source spelling, source SHA-256 and joined display wraps.
`native_header_mapping()` recognizes forms by their native header labels, not
fixed column numbers. `semester_list()` accepts explicit comma-separated integer
terms and stops on ambiguous values. No 2023 scan corrections are reused.

Row type comes from the complete source code hierarchy: parent codes are sections,
empty codes are summaries, leaves are disciplines. Section controls remain raw
counts/text and are not inherited into child rows. Preserve duplicate source
codes as separate physical rows. Inspect this classification and selected source
renderings before treating output as reviewed GT; fonts or irregular merged cells
can still affect native text extraction.

```powershell
.venv/Scripts/python.exe -m scripts.curriculum_vector_gt `
  --pdf C:/ocr/plan-2025.pdf --output C:/ocr/validation2025/gt
```

Dependency: pdfplumber. Side effects: writes page-level UTF-8 JSON under the
explicit output directory, without modifying the source PDF or production data.
Scanned pages are rejected; header-only continuation pages are skipped. Column
ambiguity, unknown codes, empty body rows and non-list term values require
explicit inspection rather than a guessed GT label. This research helper is
intentionally separate from the production PDF parser and must not be imported
into inference as a way to make predictions match evaluation answers.

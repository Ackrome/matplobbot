# CPU curriculum OCR regressions

`test_curriculum_ocr.py` tests shared raster helpers and the preserved
`parse_scanned_curriculum_legacy` reference parser's conservative semantics
and operational failure behavior independently of production servers.

`CpuCurriculumOcrTests` covers raster line detection/removal, deskewing, padded
cell-to-word assignment with wrapped names, discipline-code normalization and
rejection of joined rows, control-header recognition independent of column order,
missing/repeated header rejection, compact semester ambiguity, and a real observed
Tesseract false positive in a physically blank cell. It also validates PNG bounds,
CLI argument safety and CPU/time limits, explicit timeout/missing-engine warnings,
PDF raster selection, review-only results and clearing partial results at limits.
An explicit Tesseract TSV fixture covers opening/closing, standalone and
unclosed literal quotation marks. It verifies that later word records retain
their text, coordinates and confidence instead of being consumed as CSV quoting.

```powershell
$env:PYTHONUTF8='1'
./.venv/Scripts/python.exe -m unittest tests.test_curriculum_ocr -v
# Optional real local scan, with Tesseract and rus+eng installed:
$env:CURRICULUM_OCR_TEST_PDF='C:/path/to/official-plan.pdf'
./.venv/Scripts/python.exe -m unittest tests.test_curriculum_ocr -v
```

The default suite depends on the project's OpenCV/NumPy/Pillow/PDFium packages,
the synthetic PDF helper in `test_curriculum_documents`, and Python unittest
mocks. It never downloads data. The optional integration reads only the given
local PDF and invokes Tesseract; all OCR candidates must remain review-required.
Temporary CLI PNG files are removed by the implementation's temporary directory.
Synthetic fixtures contain no personal data. Add a focused regression for each
observed real scan failure rather than asserting a particular implementation's
entire output or calling live university URLs in CI.

The production name/CNN path is covered separately by
`test_curriculum_pipeline.py` and `test_curriculum_numeric.py`.

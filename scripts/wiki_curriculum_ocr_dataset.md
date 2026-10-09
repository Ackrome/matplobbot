# Independent OCR input export

`curriculum_ocr_dataset.py` exports one common dataset for incompatible OCR
runtimes. It never opens GT. Page rendering, OpenCV deskew, grid/header detection
and cell preprocessing are shared with the original benchmark.

`export_dataset(pdf, output, chunk_rows=12)` writes a JSON manifest, raw/clean
deskewed pages, the left table region, consecutive row chunks and every cell as
raw/clean PNG. Each row retains its independently detected ID, original-page
normalized bbox and deskew-space pixel bounds. Each cell identifies its field,
ink fraction, numeric-field flag and the existing physical blank gate. There are
no expected names, discipline types or assessment answers in the manifest.

```powershell
./.venv/Scripts/python.exe scripts/curriculum_ocr_dataset.py `
  --pdf C:/path/UP.pdf --output C:/path/ocr-input `
  --tesseract C:/path/tesseract.exe --tessdata C:/path/tessdata
```

OCR adapters may skip `blank_gate=true` control cells, but must preserve every
row and explicit missing/failed recognition. Page models can use chunks and
their geometry without reading any annotations. Score predictions separately
with `benchmark_curriculum_ocr.evaluate` only after inference finishes.

Dependencies: the existing benchmark/parser, NumPy, OpenCV, PDFium and Tesseract
for headings. No new model is downloaded, no database is touched. Writes replace
same-name artifacts only under `output`; inputs are read-only. Use separate
output directories for different sources. Source SHA256 is mandatory provenance.
Cell limits and preprocessing stay aligned with the original benchmark. Changes
to crop geometry require a new manifest version and fresh model outputs.

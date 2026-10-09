# curriculum_ocr_onnx.py

## Purpose

Optional, offline CPU recognizer for the curriculum OCR benchmark. It adds a
different recognition architecture to Tesseract comparisons without adding a
production worker dependency or publishing any inferred assessment. Model
weights and document ground truth are not included in this module.

## Public API

`OnnxCellRecognizer(model_path)` loads one local PP-OCRv5 ONNX recognizer and
exposes its SHA-256 as `model_sha256`. `recognize(graycell)` accepts a two-dimensional
`numpy.uint8` grayscale cell and returns `text`, `confidence` (0–100), `family`
(`ppocr_v5_eslav`) and elapsed `seconds`. Empty physical cells return empty text
and zero confidence. Confidence is an average character probability, not a
calibrated probability of a correct course/semester.

```python
from scripts.curriculum_ocr_onnx import OnnxCellRecognizer
reader = OnnxCellRecognizer("/local/models/eslav_PP-OCRv5_rec_mobile.onnx")
result = reader.recognize(gray_cell)
print(result["text"], result["confidence"])
```

Internal helpers split wrapped lines by horizontal ink projection, normalize
each line to PP-OCR's three-channel height-48 input, and greedily decode CTC.
They preserve text; there is no dictionary correction, semester normalization,
or ground-truth access. The caller supplies cells from its independently built
table grid.

## Dependencies and source conventions

Requires optional `onnxruntime`, `numpy`, and OpenCV. Tested locally with
`onnxruntime==1.23.2` and `opencv-python-headless==4.12.0.88`. ONNX Runtime is
imported only when constructing a recognizer. Do not add it to production
requirements merely to run this experiment.

The model is RapidAI's `eslav_PP-OCRv5_rec_mobile.onnx`, release `v3.10.0`, SHA-256
`08705d6721849b1347d26187f15a5e362c431963a2a62bfff4feac578c489aab`:
[official weights](https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/rec/eslav_PP-OCRv5_rec_mobile.onnx).
Verify weights before using a newly downloaded model; this adapter records the
actual hash and does not download anything.

The preprocessing and decoder conventions were checked against RapidOCR's
[recognizer](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/ch_ppocr_rec/main.py),
[CTC decoder](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/ch_ppocr_rec/utils.py)
and [configuration](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/config.yaml).
The embedded `character` metadata is supplemented with CTC blank at index zero
and space at the final index. Input pixels use `(pixel / 255 - 0.5) / 0.5`;
the right padding is zero in normalized coordinates. Minimum width is 320,
and wider lines retain their aspect ratio up to 2048.

## Side effects and limits

Reads the supplied model file and allocates an ONNX Runtime CPU session.
Uses only CPUExecutionProvider, sequential execution and one intra/inter-op
thread. Recognition starts a cancellable deadline timer for each inference.
It writes no files, performs no network requests and never touches the DB.

Limits: 64 MiB model, one-million-pixel cell, 4096-pixel cell edge, 12 visual
lines, 2048 normalized width and ten seconds per cell. Oversized inputs or
unsupported output/alphabet shapes fail explicitly. Runtime cancellation is
cooperative; this helper is not a replacement for OS process isolation.
Line segmentation can separate punctuation/diacritics incorrectly on degraded
scans. Raw results must be benchmarked and remain subject to source review.

## Maintenance

Keep this helper separate from production OCR until the full labelled-table
evaluation justifies promotion. Record model hash, runtime version, scenario,
latency and errors in benchmark results. Different Tesseract modes are not
different model families; this adapter supplies one independent PP-OCR family.
Tests use synthetic raster cells and mocked sessions without downloading
weights or needing ONNX Runtime installed in CI.

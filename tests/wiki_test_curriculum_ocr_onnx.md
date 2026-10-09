# test_curriculum_ocr_onnx.py

## Purpose and coverage

Offline regression tests for the optional curriculum benchmark recognizer.
`OnnxCurriculumCellTests` checks physical-blank abstention, multiline order,
CTC duplicate/blank decoding, alphabet validation, PP-OCR pixel normalization,
CPU-only thread configuration, input bounds and timeout propagation.

These tests intentionally verify actual OCR adapter boundaries rather than
asserting model accuracy from fabricated predictions. Accuracy is measured
separately on visually labelled real scans by the benchmark.

## Usage

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m unittest tests.test_curriculum_ocr_onnx -v
```

## Dependencies and side effects

Uses standard-library unittest/mock/tempfile plus numpy and OpenCV. Sessions
are mocked: ONNX Runtime and real model weights are not required, and no
network requests occur. Temporary mock model files are cleaned automatically.

## Maintenance

Keep the expected embedded alphabet order and normalized padding aligned with
the documented RapidOCR model conventions. Synthetic fixtures must not contain
private documents or encode the GT answer as recognizer logic. Add real model
performance observations to the benchmark report, not fragile CI timing tests.

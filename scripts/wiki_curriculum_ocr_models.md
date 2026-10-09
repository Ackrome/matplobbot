# Optional CPU OCR model comparison adapters

`curriculum_ocr_models.py` is an offline experimental runner. It is not imported
by the production curriculum worker. It consumes local verified weights and a
GT-free table-cell manifest produced by `curriculum_ocr_dataset.py`, or reconstructs
the grid from a PDF with the existing benchmark detector. It does not load GT,
course dictionaries or expected semester values, and does not download models.

## Public interface

- `PaddleCellRecognizer(model_path, family=..., numeric=False,
  controls_only=False)` runs PP-OCRv3/v5/v6 recognition ONNX exports on CPU.
  The embedded CTC alphabet and tensor shapes are checked. Models lacking a
  Russian alphabet require `controls_only=True`; identity cells then explicitly
  abstain. All tested official exports use RGB NCHW height 48.
- `EasyCellRecognizer(model_directory, generation=1|2, numeric=False)` loads
  EasyOCR Cyrillic weights locally, without a detector, on CPU with dynamic
  quantization. Both generations are different checkpoints, not independent
  training architectures.
- `constrained_ctc(probabilities, alphabet, numeric=True)` permits only digits,
  separators and the blank class in numeric fields. It masks CTC label choices,
  not the input image or source string. A letter such as `з` is never blindly
  replaced with `3`; the original model probability of the chosen digit is kept.
  No 1–8 limit is imposed because section totals are also in the test set.
- `predict_dataset(...)` preserves all physical rows and their original-page
  boxes, applies the frozen blank gate, and records unsupported/invalid cell
  abstentions. Paths must stay in the exported dataset directory.
- `main()` writes one JSON scenario with raw readings, native/constrained line
  evidence, hashes, initialization/inference time and sampled process peak RSS.
  It has no GT argument; score results separately with the central evaluator.

```powershell
.venv/Scripts/python.exe -m scripts.curriculum_ocr_models `
  --dataset C:/ocr/dataset/manifest.json --output C:/ocr/results `
  --model C:/ocr/models/cyrillic_PP-OCRv5_rec_mobile.onnx `
  --family ppocr_v5_cyrillic_numeric --numeric --workers 2
```

EasyOCR uses `--easyocr-generation 2 --model C:/ocr/models/easyocr --workers 1`.
Optional `--package-path` appends an isolated runtime's site-packages, allowing
the project Python to orchestrate experiments without changing locked production
dependencies. Omit it when the optional dependencies are installed normally.
`--preprocessing clean|raw|otsu` selects the visual preprocessing independently
of expected answers.

## Dependencies, model provenance and limits

Common optional dependencies: NumPy, OpenCV, psutil. ONNX: onnxruntime CPU.
EasyOCR: easyocr, torch, torchvision and EasyOCR's dependencies. PDF input also
needs pypdfium2 and configured Tesseract for rotated table headers. Frozen
dataset input does not rerender the PDF or invoke Tesseract.

Official model registry:
[RapidAI default_models.yaml](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/default_models.yaml).
Downloaded ONNX files are checked against that registry's SHA-256 hashes by the
experiment preparation step; each output records its actual model hash.
EasyOCR checkpoints come from
[the upstream recognition configuration](https://github.com/JaidedAI/EasyOCR/blob/master/easyocr/config.py).
The checkpoint's official MD5 and an independently recorded SHA-256 were checked.
Only load trusted model files: a model runtime is not a file-content sandbox.

ONNX files are limited to 128 MiB, EasyOCR checkpoints to 256 MiB, alphabets to
25,000 classes, dataset rows to 5,000, workers to 1–8, and visual cells/line width
use `curriculum_ocr_onnx` bounds. Execute the runner in a bounded child process
for hard time/RAM isolation; Python thread cancellation is not OS isolation.
The sampled RSS includes the selected runtime/model and cell inference, but
frozen-dataset runs exclude PDF geometry memory and already-exported images.
Windows Torch imported from a CUDA-capable installation still runs this adapter
on CPU; its process size is not the Linux CPU-only wheel's memory requirement.

PP-OCRv6 tiny/small/medium do **not** provide Russian in their documented
[language list](https://www.paddleocr.ai/latest/en/version3.x/algorithm/PP-OCRv6/PP-OCRv6.html).
They are evaluated here solely as numeric-control experts, never as Russian
discipline recognizers. Two decoding modes of one checkpoint are correlated
views, not two independent model votes. Numeric masking probabilities are not
calibrated confidence; evaluate all blank cells and retain disagreements.

Output JSON and temporary runtime files are the only side effects. No imports,
publication, administrator fields, database records or production dependencies
are changed. Before recommending a checkpoint, inspect strict identity/fact
metrics, false additions to blank cells, and actual deployment RAM/CPU ISA.

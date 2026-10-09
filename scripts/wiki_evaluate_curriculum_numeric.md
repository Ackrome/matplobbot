# Independent numeric-cell and assessment evaluation

`evaluate_curriculum_numeric.py` separates inference from scoring. Printed source
discipline indices do not participate in end-to-end identity: the strict key is
**page + physical row geometry + discipline name + control kind + semester**.
Duplicate names/indices on another row cannot overwrite each other.

## Public functions and commands

- `infer_numeric(dataset_path, model_path, metadata_path, output_path)` invokes
  `read_control_cell()` with `NumericRecognizer` on every control cell, including
  all blanks and explicitly separated wrapped lines. It has
  no GT parameter, does not OCR names/indices/headers, and does not use the old
  exported blank gate to make results look better. The geometry manifest must
  explicitly declare `gt_used=false` and contain all five control fields.
- `validate_model_provenance()` requires synthetic-only training, named training
  sources and an exact frozen weight hash. Model, metadata and dataset hashes are
  checked again after inference. These checks audit declared provenance; they are
  not cryptographic proof about the historical contents of a training dataset.
- `score_numeric_cells()` evaluates every literal numeric/blank cell, including
  section counts, separately from semester semantics on discipline rows. Missing
  cells and abstentions never count as correct blanks. It reports raw and semantic
  additions to blanks separately, coverage, invalid strings and extra rows.
- `score_assessments()` penalizes wrong names/kinds/terms with both FP and FN.
  Row alignment is one-to-one by page, x-IoU >= 0.5 and y-IoU >= 0.45; labels and
  printed codes do not select matches. Name normalization only uses Unicode NFKC,
  case and whitespace: there is no fuzzy dictionary or Cyrillic/Latin substitution.
  Unknown row classification suppresses emission and is counted explicitly.
- `render_contacts()` creates PNG contact sheets from the actual frozen input
  cells, plus separate sheets for every error/abstention. Only this scoring stage
  reads GT. The exported PNGs are review artifacts, not training input.

```powershell
# Stage 1: GT-free inference, complete output appears only after all cells finish.
.venv/Scripts/python.exe -m scripts.evaluate_curriculum_numeric infer `
  --dataset C:/ocr/dataset/manifest.json `
  --model shared_lib/data/curriculum_numeric.onnx `
  --metadata shared_lib/data/curriculum_numeric.json `
  --output C:/ocr/frozen-predictions.json

# Stage 2: score immutable predictions in another invocation.
.venv/Scripts/python.exe -m scripts.evaluate_curriculum_numeric score `
  --predictions C:/ocr/frozen-predictions.json `
  --gt C:/ocr/gt/page1.json C:/ocr/gt/page2.json `
  --contact-dataset C:/ocr/dataset/manifest.json --output C:/ocr/metrics.json
```

For full parser audit rows, provide the complete pipeline result (`complete=true`,
source SHA-256, `rows` containing names, `is_discipline` and control-cell readings)
to `score --end-to-end`. Numeric-only inference intentionally has no names or row
classification and should not be described as end-to-end accuracy.

## Dependencies, effects and maintenance

Pure scoring uses the Python standard library. Inference additionally requires
OpenCV and the optional CPU recognizer/runtime; PNG reports require Pillow and a
system font. No network calls, publication, database writes or model updates occur.
Explicit outputs and `.partial.json` checkpoints are the only side effects.
Partial/incomplete/unmarked runs cannot receive CLI scores. Existing complete
output files are not overwritten: use a new filename for each frozen experiment.

The source hash of every GT page must match the prediction's source hash. GT keys
such as `expected_text`, `semesters`, `row_type` and `controls` are rejected in the
image manifest. Do not send real GT answers to the synthetic training process,
change acceptance thresholds based on test errors, or count model-selection data
as untouched held-out validation. Native 2025 PDF rasterization is a clean-layout
regression probe, not a new noisy-scan benchmark. Keep both statements visible in
reports. Header extraction in `curriculum_vector_gt.py` is evaluation-only;
production inference uses explicit layout profiles and never OCRs headers/indexes.

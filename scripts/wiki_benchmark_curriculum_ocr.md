# CPU curriculum OCR benchmark

`benchmark_curriculum_ocr.py` is an offline experiment runner. It compares the
existing batched parser with per-cell Tesseract fast/best, PSM 6/7, deskew and
preprocessing ablations, optional PP-OCRv5 ONNX recognition, and conservative
multiple-checkpoint consensus. It does not change production settings or publish data.

## Entry points

- `detect_pages`: PDFium rasterization, independent OpenCV grid/header detection,
  page deskew and normalized row geometry transformed back to original page space.
- `CellEngine.read`: bounded Tesseract invocation and content/config/model-hash cache.
- `predict`: every physical row, including sections and blank control cells.
- `consensus`/`ensemble`: distinct checkpoints vote; internally conflicting views
  abstain. Disagreement stays visible instead of being silently treated as blank.
- `evaluate`: one-to-one page/y IoU row alignment; raw cells, semantic discipline
  controls, missing rows, extra facts, false-positive blanks, CER and ANLS.
  Geometry-based facts, strict canonical-code facts and strict code+title facts
  are separate metrics: a correct numeral assigned to a wrong code is an error.
  Row-classifier TP/FP/FN/TN and missing rows are also reported, including rows
  with five empty controls. Missing classifications are separate from the four
  confusion-matrix cells; recall-with-missing includes missing positive rows.
- `match_name`: lexical suggestion with minimum similarity 0.90 and margin 0.08.
  Raw OCR remains intact. A GT-derived dictionary is explicitly an oracle upper
  bound with leakage, never an independent correction experiment.

`ensemble3_semantic` is an exploratory, unvalidated-on-held-out-data variant:
code votes use the existing parser normalization; controls vote on unambiguous
semester tuples; invalid numeric strings abstain; same-cell title hypotheses use
a medoid neighborhood at similarity 0.95. It never reads GT or the dictionary.
The three model checkpoints represent two architectures (Tesseract and PP-OCR),
and two PSM settings of a checkpoint never provide two independent votes.

`hybrid_fields_development` routes fields to fixed saved predictions: codes from
`best_clean6`, names from the batched `baseline`, and all five controls from
`onnx_clean`. Fusion takes no GT input and retains per-cell source provenance.
This hypothesis was deliberately selected after seeing aggregate performance on
the same GT, so its evaluation is development-set performance, not a held-out
claim or production adoption. `--evaluate-only` can build/score it from existing
predictions with no new OCR. Its reported runtime sums the complete constituent
runs; it does not claim a measured optimized field-only pipeline time.

## Usage

Run from the project root with the project virtual environment (UTF-8 enabled):

```powershell
./.venv/Scripts/python.exe scripts/benchmark_curriculum_ocr.py `
  --pdf C:/path/UP.pdf --output C:/path/benchmark `
  --tesseract C:/path/tesseract.exe `
  --fast-model C:/path/tessdata_fast --best-model C:/path/tessdata_best `
  --onnx-model C:/path/eslav_PP-OCRv5_rec_mobile.onnx `
  --gt tests/fixtures/curriculum_ocr/fa_pmo_2023_page1_gt.json tests/fixtures/curriculum_ocr/fa_pmo_2023_page2_gt.json `
  --dictionary C:/path/independent_ruz_names.json --workers 2
```

Use `--evaluate-only` to score saved predictions without rerunning inference.
`--scenarios` accepts a comma-separated subset of the default names. Models are
not downloaded automatically. Tesseract fast/best 4.1.0 language weights are
separate families within the same engine, not independent OCR architectures.

## Protocol, dependencies and limitations

GT files are read only after inference. Hash mismatch or unverified GT rows abort
scoring. GT does not select rows, grid lines, headers or OCR crops. The saved
geometry makes missed/merged rows auditable. Physical rows with no assessments
remain in raw predictions; a separate conservative production-like row classifier
determines emitted facts. Sections contain counts, so their cells are scored as
literal text and never converted to assessment facts.
Every preprocessing scenario uses the same physical-ink blank gate from the
rule-cleaned cell; the raw/clean/Otsu ablation changes OCR input, not that gate.
`production-candidate-metrics.json` separately scores exactly what the existing
parser emits. Raw-cell baseline metrics are a proxy with extra diagnostics;
candidate identity uses the parser's existing trailing-rule text cleanup while
raw name accuracy does not.
Production candidate boxes originate in deskewed page coordinates; evaluation
inverts the saved page rotation before matching original-page GT. Saved alignment
records contain both boxes and the resulting row match.

ANLS lowercases strings while preserving whitespace and uses `1 - normalized edit
distance` only for distance strictly below 0.5; otherwise zero. Dictionary matching
additionally normalizes whitespace and has a stricter acceptance threshold.
Source: [ST-VQA definition reproduced in InfographicVQA supplement](https://openaccess.thecvf.com/content/WACV2022/supplemental/Mathew_InfographicVQA_WACV_2022_supplemental.pdf).

Dependencies are OpenCV, NumPy, pypdfium2, installed Tesseract rus/eng models, the
project parser, and optionally ONNX Runtime plus `curriculum_ocr_onnx.py`. Each
Tesseract child has a 30-second timeout and a single OpenMP thread. Workers are
bounded to 1–8. No GPU is used. Cache hits affect measured wall time; inspect
per-cell `cache_hit`, scenario `timing.kind` and stored original inference seconds.
ONNX engine metadata/cache keys include the actual installed ONNX Runtime version.
Each scenario has its own cache directory to avoid cross-scenario timing bias.
`inference_seconds` excludes geometry; `pipeline_seconds` adds shared rendering,
deskew/grid/header time once. Neither includes model initialization. Ensemble
time is the sum of constituent scenarios plus fusion, not an additional model.

Outputs include model hashes, engine version, original predictions, geometry,
the stock production candidates, metrics JSON/CSV, per-row error details and
dictionary suggestions. Source files are read-only; outputs/cache are written
only under the supplied directory. No database/network operations are performed.
Single-plan tuning is not a generalization claim; validate held-out plans before
promoting changes to production. Bump `BENCHMARK_VERSION` when cell preprocessing
or cache semantics change, and keep missing rows and blank errors in denominators.
Benchmark version 3 disables CSV quote interpretation for Tesseract TSV: literal
OCR quotes must not swallow following rows. Version 2 historical results are
preserved separately; comparisons after the reader fix use a fresh cold output.
An oversized or timed-out cell is an explicit abstention with error details;
it is not scored as a correctly recognized blank and does not vote in ensembles.
Dictionary evaluation sweeps similarities 0.75/0.85/0.90/0.95 and margins 0.03/0.08
and records correct/incorrect suggestions, fixes, harmful changes and coverage.

The saved `production-candidates.json` comparison explicitly invokes
`parse_scanned_curriculum_legacy` after the name/CNN pipeline became the default.
This preserves historical baseline semantics instead of silently changing the
meaning of the benchmark. Run `run_curriculum_pipeline.py` for the current parser.

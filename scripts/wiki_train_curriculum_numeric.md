# Train the small numeric CNN+CTC

`train_curriculum_numeric.py` is a reproducible synthetic-only training/export
tool. It does not accept PDFs, OCR predictions, annotated cells or curriculum GT.
The only image sources are installed font files and procedurally generated
numeric strings, including empty values, lists, numbers, ranges and a dash.

`synthetic_cell` varies font, size, weight, aspect, paper contrast/gradient,
resolution, skew, blur, grain, isolated specks and line remnants. `SyntheticDataset`
uses deterministic per-sample seeds. Cases outside the runtime width bound are
resampled deterministically; they are not forced through aspect distortion.
`make_model` constructs four convolutional image blocks plus temporal convolutions
and a CTC head. There is no recurrent layer or general-language OCR model.
`validate` checks exact strings on independent seeds and partly held-out fonts.

Example from the project virtual environment, with optional separate training
packages to avoid changing application dependencies:

```powershell
./.venv/Scripts/python.exe scripts/train_curriculum_numeric.py `
  --output C:/runs/numeric-synthetic --device cuda --steps 4000 `
  --package-path C:/path/to/training/site-packages
```

Training requires Torch, Pillow, NumPy, OpenCV and ONNX. CUDA is optional for
training only; `--device cpu` works as well. The exported ONNX model is intended
for single-threaded CPU ONNX Runtime. Windows font names are explicitly selected
and recorded; supply `--fonts` with matching legally installed font files on
other systems. Font files are not bundled or redistributed.

Outputs: periodic state-dict checkpoints, final weights, raw synthetic validation
predictions, ONNX and metadata with weights/source hashes, seeds, fonts, parameter
count, confidence threshold and exact/accepted validation counts. No production
settings or database are modified. Copy the final ONNX/JSON into packaged data
only after ONNX/PyTorch CPU parity and model-size checks pass. Freeze the hash
before a separate evaluator opens real-table GT; retain failed runs rather than
quietly retraining against their expected labels.

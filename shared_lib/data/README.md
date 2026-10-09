# Packaged curriculum numeric model

`curriculum_numeric.onnx` and `curriculum_numeric.json` are a matched immutable
weight/metadata pair. `setup.py` includes both in the wheel; only the scheduler
installs ONNX Runtime. No model download happens at runtime.

The 121,277-parameter convolutional CTC model reads `0123456789,-` sequences in
prepared control cells. It cannot read names, headers or printed course indices.
Model size: 488,345 bytes. SHA256:
`88bc1d21d5cc709db75a17e2ef8cf2ffd695b0b8e6b22c3c40f6de4265bc8c01`.

Training used 384,000 generated font/noise samples, no real curriculum images,
GT, or OCR predictions. The JSON records seeds, training settings, source hashes
and validation metrics. Installed font files were used locally and are not
redistributed. Training source hashes describe the exact files at training time;
any later source change must be distinguished from the frozen training provenance.

See [the validation report](../../docs/reports/curriculum-numeric-pipeline/README.md)
for real document results, preprocessing failures, export parity, server resource
measurements and reproduction commands. In particular, raw noisy cells with grid
remnants are outside the model's validated production input contract.

Maintain the paired SHA check, bounded image dimensions and abstention behavior.
Retrain through `scripts/train_curriculum_numeric.py` into a separate directory,
freeze the model before real-GT scoring, then explicitly copy validated assets.
Do not train on a benchmark and report that benchmark as an independent test.

# Run the numeric curriculum pipeline

`run_curriculum_pipeline.py` runs the exact production parser outside the queue,
for reproducible local CPU validation. `main()` accepts a PDF, an output JSON,
an optional declared `--scan-layout`, and local Tesseract executable/data paths.
There is intentionally no GT or expected-value argument.

```powershell
.venv/Scripts/python.exe scripts/run_curriculum_pipeline.py --pdf plan.pdf `
  --scan-layout fa_legacy_v1 --output output/predictions.json
```

Dependencies and constraints are those of `curriculum_pipeline`. It writes only
the requested result and creates its parent directory; local OCR uses temporary
files. It neither installs dependencies nor downloads model weights. Exit 2
means no assessment candidates were produced; read the persisted warnings.
Score this frozen JSON in a separate evaluation step. The scheduler remains
responsible for a subprocess-wide memory/CPU/wall-time limit in production.

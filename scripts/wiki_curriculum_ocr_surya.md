# Optional Surya CPU benchmark adapters

`curriculum_ocr_surya.py` supplies isolated offline OCR adapters. It does not
import models into the application, download weights, change production OCR,
read GT, or correct text from an answer dictionary.

- `Surya1Recognizer` loads a caller-supplied classic 0.17.1 checkpoint on CPU,
  caps threads/batch size, and recognizes whole cell boxes. Wrapped text remains
  visible to the model. `recognize_batch` retains raw markup as `raw_model_text`
  and exposes plain visible `text`, confidence and time. The classic API can
  embed literal `<br>`/`<b>` tags; comparing these to a plain-text GT without
  HTML normalization would mislabel formatting as recognition errors.
  Optional dynamic INT8 is a separately named experimental variant. Its initial
  FP32 load still needs the full memory footprint; quantization is not a promise
  that startup fits a smaller VM.
- `Surya2Client` calls a separately started llama.cpp server with the official
  exact block prompt. It preserves HTML, usage and finish reason. Truncated
  responses abstain; HTML is treated as inert text by `html_text`.

Example (inside an isolated classic Surya environment):

```python
from PIL import Image
from scripts.curriculum_ocr_surya import Surya1Recognizer
recognizer = Surya1Recognizer('/models/text_recognition/2025_09_23')
result = recognizer.recognize_batch([Image.open('/tmp/cell.png')])
```

Example Surya 2 call, after CPU backend startup:

```python
from scripts.curriculum_ocr_surya import Surya2Client
result = Surya2Client('http://127.0.0.1:18976/v1').recognize(image)
```

The executable manifest runner never accepts GT. Export cells first using
`curriculum_ocr_dataset.py`, then run:

```powershell
./.venv/Scripts/python.exe scripts/curriculum_ocr_surya.py `
  --manifest C:/runs/dataset/manifest.json --output C:/runs/surya2 `
  --backend surya2 --endpoint http://127.0.0.1:18976/v1 --server-pid 1234 `
  --family-label surya2_gguf_f16
```

For classic Surya use `--backend surya1 --checkpoint C:/models/2025_09_23`
and optional repeated `--package-path` arguments to a separate compatible
package directory. `--threads 4 --batch-size 4` bound concurrency. `--max-cells`
is smoke-only and leaves unprocessed cells explicitly abstained; it never yields
a falsely complete result. Score the saved predictions separately with the
frozen GT and `benchmark_curriculum_ocr.evaluate`.

The bounded HTTP runner can also evaluate another compatible OCR backend with
explicit publisher settings, for example `--prompt OCR: --model-label paddle
--family-label paddleocr_vl_1_5`. The default prompt/alias remains Surya. Record
the actual model revision, quantization and prompt in the experiment manifest;
the adapter name alone does not identify external server weights.

Outputs are `predictions.json`, `partial.json` and `progress.json` beneath the
chosen output directory. All physical rows and controls remain represented.
Blank gates are inherited unchanged from independent geometry preprocessing.
Memory sampling distinguishes client from a caller-supplied backend PID; for
Windows the process counters include kernel-recorded peak working set. On other
systems sampled RSS is a lower bound for peak. Run model processes with an
external hard deadline/memory limit when required; classic Torch inference is
not forcibly cancelled by this adapter.

For a memory-bounded llama.cpp server, explicitly disable request-state caching:

```text
llama-server -m surya-2.gguf --mmproj surya-2-mmproj.gguf
  -ngl 0 --no-mmproj-offload -t 4 -tb 4 -c 4096 --parallel 1
  --host 127.0.0.1 --port 18976 --alias surya2 --no-webui
  --cache-ram 0 --no-cache-prompt --no-cache-idle-slots
```

In the 2026-10-09 experiment, b11529's default 8192 MiB prompt cache grew the
process from roughly 1.6 GiB RSS to 5.9 GiB after 110 different cells. This is
not the model's minimal working set; retain the flags and measure the complete
queue, not one successful cell. Windows CPU b11529 includes an SSE4.2 plugin;
a smoke test used only `ggml-cpu-sse42.dll` among CPU variants and confirmed that
loaded module. This establishes an ISA path, not production Linux validation.

Classic dependencies conflict with current Surya: never downgrade the project
environment. Use a separate package/runtime path and record package versions.
Surya 2 HTTP calls require only the standard library and Pillow in this adapter;
the official GGUF model and matching multimodal projector are separate assets.
The backend must explicitly use CPU (`-ngl 0 --no-mmproj-offload`) to label a run
CPU. Record model hashes and peak resident RAM, not just file size. HTTP timeout
does not itself prove upstream cancellation; manage the separate backend process
and bound the total offline run. No transparent retries are performed.

Maintenance: retain exact publisher prompts, lazy heavy imports, raw output,
non-normal termination handling, and independent geometry/GT scoring. A single
development table is not a held-out quality claim.

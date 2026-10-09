# GLM-OCR CPU experiment

`curriculum_ocr_glm.py` evaluates the official `ggml-org/GLM-OCR-GGUF` Q8 model
through a caller-provided llama.cpp server binary. It reads only the independently
detected grid manifest and its original table chunks; GT, discipline vocabularies
and expected assessment values never enter inference. This is an offline research
tool, not a production parser.

## Interface and use

```powershell
.venv/Scripts/python.exe scripts/curriculum_ocr_glm.py --server-bin C:/models/llama-server.exe --model C:/models/GLM-OCR-Q8_0.gguf --mmproj C:/models/mmproj-GLM-OCR-Q8_0.gguf --manifest C:/inputs/manifest.json --output C:/results/glm --limit-chunks 1
```

`run(args)` starts a private localhost CPU server and submits the model's official
`Table Recognition:` prompt. `parse_table(text)` expands one complete HTML table;
`map_chunk(...)` maps its columns using OCR-detected headers. The mapper requires
exact geometric row/column counts and rejects ambiguous/truncated tables instead
of silently shifting all following assessments. Merged labels occupy their first
column and first physical row; continuations remain blank. In particular, a
section-level assessment is not copied into its child discipline rows.

## Dependencies, effects and maintenance

Python 3.11+, requests and psutil are required; llama.cpp and two GGUF files are
explicit local inputs, with SHA256 recorded. The script does not download models,
install dependencies, read GT, or change any application data. It starts one
temporary localhost server, writes raw responses, mapped rows, server logs and
startup/latency/RSS evidence under `--output`, then kills its own process tree.
The default port is 18978; use a free port. CPU inference uses two threads, no GPU
layers and no vision-projector offload. llama.cpp prompt/idle-slot caches are
disabled and `--cache-ram 0` prevents its otherwise large default cache from
accumulating across independent images. RSS is sampled every 100 ms and the default
3 GiB threshold triggers termination; this sampled guard is not an OS allocation
limit. Each request and startup also have deadlines. Raw model responses remain
available even when strict geometric mapping fails.

Pin and verify model and binary revisions for comparisons. Image pixels must not
be replaced using evaluation annotations. A local Windows result does not prove
compatibility/performance on the production VM's limited CPU instruction set.
Sources: [official model and task prompts](https://huggingface.co/zai-org/GLM-OCR),
[official llama.cpp conversion](https://huggingface.co/ggml-org/GLM-OCR-GGUF).

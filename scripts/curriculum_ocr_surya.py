"""Optional Surya CPU adapters for offline curriculum OCR experiments.

No ground truth, discipline dictionary or expected control values enter these
adapters. Heavy dependencies are lazy so normal application imports stay small.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import io
import json
import os
import sys
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


class _PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"p", "div", "br", "tr", "td", "th", "li"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"p", "div", "tr", "td", "th", "li"}:
            self.parts.append(" ")

    def handle_data(self, data):
        self.parts.append(data)


def html_text(value: str) -> str:
    """Extract visible OCR text without executing model-produced HTML."""
    parser = _PlainHTML()
    parser.feed(value)
    parser.close()
    return " ".join("".join(parser.parts).split())


class Surya1Recognizer:
    """Classic Surya 0.17.1, CPU-only, accepting cells as whole OCR regions."""

    family = "surya1_2025_09_23"

    def __init__(self, checkpoint, *, threads=4, batch_size=4, quantize=False):
        if not 1 <= threads <= 16 or not 1 <= batch_size <= 32:
            raise ValueError("CPU threads/batch size exceed the benchmark bounds.")
        import torch
        from surya.foundation import FoundationPredictor
        from surya.recognition import RecognitionPredictor

        torch.set_num_threads(threads)
        torch.set_num_interop_threads(1)
        started = time.monotonic()
        self.foundation = FoundationPredictor(
            checkpoint=str(checkpoint), device="cpu", dtype=torch.float32
        )
        if quantize:
            # Explicit experimental variant, never silently applied to FP32.
            self.foundation.model = torch.ao.quantization.quantize_dynamic(
                self.foundation.model,
                {torch.nn.Linear},
                dtype=torch.qint8,
                inplace=True,
            )
            self.family += "_dynamic_int8"
        self.predictor = RecognitionPredictor(self.foundation)
        self.predictor.disable_tqdm = True
        self.batch_size = batch_size
        self.initialization_seconds = time.monotonic() - started

    def recognize_batch(self, images):
        """Recognize equally unprivileged cells; no text correction is applied."""
        if not images or len(images) > self.batch_size:
            raise ValueError("Expected a nonempty bounded image batch.")
        converted = []
        for image in images:
            if not 0 < image.width * image.height <= 1_000_000:
                raise ValueError("Cell exceeds one million pixels.")
            converted.append(image.convert("RGB"))
        started = time.monotonic()
        results = self.predictor(
            converted,
            bboxes=[[[0, 0, image.width, image.height]] for image in converted],
            recognition_batch_size=self.batch_size,
            math_mode=False,
            max_tokens=192,
            return_words=False,
        )
        elapsed = time.monotonic() - started
        return [
            {
                "text": html_text(" ".join(line.text for line in result.text_lines)),
                "raw_model_text": " ".join(line.text for line in result.text_lines).strip(),
                "confidence": 100
                * min((float(line.confidence) for line in result.text_lines), default=0),
                "family": self.family,
                "seconds": elapsed / len(results),
                "batch_seconds": elapsed,
                "cache_hit": False,
            }
            for result in results
        ]


class Surya2Client:
    """Bounded llama.cpp OpenAI client using Surya's exact block OCR prompt.

    Start the backend separately with CPU offload disabled. The client cannot
    prove its backend's hardware configuration; record the server command/log.
    """

    family = "surya2_external_gguf"
    prompt = "OCR this block image to HTML."

    def __init__(
        self, endpoint, *, timeout=180, max_tokens=2048, model_label="surya2", prompt=None
    ):
        if not 1 <= timeout <= 600 or not 32 <= max_tokens <= 12288:
            raise ValueError("Request limits exceed the benchmark bounds.")
        self.endpoint = endpoint.rstrip("/") + "/chat/completions"
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.model_label = model_label
        if prompt is not None:
            self.prompt = prompt
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def recognize(self, image):
        if not 0 < image.width * image.height <= 8_000_000:
            raise ValueError("Image exceeds eight million pixels.")
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        payload = {
            "model": self.model_label,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64," + encoded},
                        },
                        {"type": "text", "text": self.prompt},
                    ],
                }
            ],
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
            "stream": False,
        }
        started = time.monotonic()
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with self.opener.open(request, timeout=self.timeout) as response:
            body = response.read(16 * 1024 * 1024 + 1)
        if len(body) > 16 * 1024 * 1024:
            raise ValueError("Model response exceeded the response size limit.")
        data = json.loads(body)
        choice = data["choices"][0]
        raw = choice["message"].get("content") or ""
        ended = choice.get("finish_reason") == "stop"
        return {
            "text": html_text(raw) if ended else "",
            "raw_html": raw,
            "confidence": 0,
            "family": self.family,
            "abstained": not ended,
            "error": None if ended else "Model output did not terminate normally.",
            "finish_reason": choice.get("finish_reason"),
            "usage": data.get("usage", {}),
            "timings": data.get("timings", {}),
            "seconds": time.monotonic() - started,
            "cache_hit": False,
        }


def main(argv=None):
    """Run a GT-free exported cell manifest through one selected CPU backend."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", choices=("surya1", "surya2"), required=True)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--endpoint", default="http://127.0.0.1:18976/v1")
    parser.add_argument("--package-path", type=Path, action="append", default=[])
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--quantize", action="store_true")
    parser.add_argument("--server-pid", type=int)
    parser.add_argument("--max-cells", type=int)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--max-tokens", type=int, default=192)
    parser.add_argument("--family-label", help="Explicit backend weight/quantization label.")
    parser.add_argument("--model-label", default="surya2", help="OpenAI backend model alias.")
    parser.add_argument("--prompt", help="Explicit publisher prompt for another OCR checkpoint.")
    args = parser.parse_args(argv)
    if args.backend == "surya1" and not args.checkpoint:
        parser.error("--checkpoint is required for classic Surya.")
    if args.max_cells is not None and args.max_cells < 1:
        parser.error("--max-cells must be positive.")
    if args.quantize and args.backend != "surya1":
        parser.error("--quantize is only the classic PyTorch experimental variant.")
    # Local package overlays keep incompatible v1 dependencies out of the app.
    sys.path[:0] = [str(p.resolve()) for p in args.package_path]
    repository = str(Path(__file__).resolve().parents[1])
    if repository not in sys.path:
        sys.path.insert(0, repository)
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["TORCH_DEVICE"] = "cpu"
    import psutil
    from PIL import Image

    from scripts.benchmark_curriculum_ocr import classify_rows

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("gt_used") is not False:
        raise ValueError("Expected an independently exported gt_used=false manifest.")
    base = args.manifest.resolve().parent
    rows = copy.deepcopy(manifest["rows"])
    jobs = []
    for row in rows:
        for field, cell in row["cells"].items():
            if cell["blank_gate"]:
                row["cells"][field] = {
                    "text": "",
                    "confidence": 0,
                    "seconds": 0,
                    "blank_gate": True,
                    "family": args.backend,
                    "ink_fraction": cell["ink_fraction"],
                }
            else:
                path = (base / cell["clean_path"]).resolve()
                if not path.is_relative_to(base):
                    raise ValueError("Cell path must stay inside the exported dataset.")
                jobs.append((row, field, path, cell["ink_fraction"]))
                row["cells"][field] = {
                    "text": "",
                    "abstained": True,
                    "error": "Not processed.",
                    "confidence": 0,
                    "family": args.backend,
                }
    jobs_to_run = jobs[: args.max_cells] if args.max_cells else jobs
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    if args.backend == "surya1":
        recognizer = Surya1Recognizer(
            args.checkpoint,
            threads=args.threads,
            batch_size=args.batch_size,
            quantize=args.quantize,
        )
        batch_size = args.batch_size
    else:
        recognizer = Surya2Client(
            args.endpoint,
            timeout=args.timeout,
            max_tokens=args.max_tokens,
            model_label=args.model_label,
            prompt=args.prompt,
        )
        batch_size = 1
    if args.family_label:
        recognizer.family = args.family_label
    initialization_seconds = time.monotonic() - started
    started = time.monotonic()
    process = psutil.Process(args.server_pid) if args.server_pid else psutil.Process()
    memory_scope = "backend" if args.server_pid else "client"
    rss_peak_sampled = 0
    for first in range(0, len(jobs_to_run), batch_size):
        batch = jobs_to_run[first : first + batch_size]
        images = [Image.open(job[2]) for job in batch]
        try:
            if args.backend == "surya1":
                values = recognizer.recognize_batch(images)
            else:
                values = [recognizer.recognize(images[0])]
        except Exception as exc:
            values = [
                {
                    "text": "",
                    "confidence": 0,
                    "abstained": True,
                    "family": recognizer.family,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                for _ in images
            ]
        finally:
            for image in images:
                image.close()
        if len(values) != len(batch):
            raise ValueError("Recognizer returned a different number of cells.")
        for (row, field, _, ink), value in zip(batch, values):
            row["cells"][field] = dict(value, ink_fraction=ink)
        memory = process.memory_info()._asdict()
        rss_peak_sampled = max(rss_peak_sampled, memory["rss"])
        progress = {
            "completed": min(first + batch_size, len(jobs_to_run)),
            "total": len(jobs),
            "seconds": time.monotonic() - started,
            "memory_scope": memory_scope,
            "memory": memory,
        }
        (args.output / "progress.json").write_text(json.dumps(progress), encoding="utf-8")
        (args.output / "partial.json").write_text(
            json.dumps(rows, ensure_ascii=False), encoding="utf-8"
        )
        if first % 20 == 0:
            print(json.dumps(progress), flush=True)
    result = {
        "name": recognizer.family + "_clean",
        "source_sha256": manifest["source_sha256"],
        "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "gt_used": False,
        "complete": len(jobs_to_run) == len(jobs),
        "rows": classify_rows(rows),
        "timing": {
            "initialization_seconds": initialization_seconds,
            "inference_seconds": time.monotonic() - started,
            "threads": args.threads if args.backend == "surya1" else "external backend",
            "batch_size": batch_size,
        },
        "memory_scope": memory_scope,
        "memory": process.memory_info()._asdict(),
        "rss_peak_sampled": rss_peak_sampled,
        "scope": "Offline CPU experiment; backend initialization excluded for Surya 2.",
    }
    (args.output / "predictions.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

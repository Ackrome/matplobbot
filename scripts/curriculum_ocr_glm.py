"""Bounded, CPU-only GLM-OCR GGUF experiment on independently exported table chunks.

Only input geometry and images are read. Evaluation labels never enter the model
or the output mapper. This offline tool is not imported by production services.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import threading
import time
from html.parser import HTMLParser
from pathlib import Path

PROMPT = "Table Recognition:"
MAX_IMAGE_BYTES = 8 * 1024 * 1024


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            if self.table is not None:
                raise ValueError("Nested tables are unsupported")
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            a = dict(attrs)
            colspan, rowspan = int(a.get("colspan", "1")), int(a.get("rowspan", "1"))
            if not 1 <= colspan <= 20 or not 1 <= rowspan <= 100:
                raise ValueError("Invalid table span")
            self.cell = {"parts": [], "colspan": colspan, "rowspan": rowspan}
        elif tag == "br" and self.cell is not None:
            self.cell["parts"].append(" ")

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["parts"].append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.cell["text"] = " ".join("".join(self.cell.pop("parts")).split())
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def parse_table(text: str) -> list[list[str]]:
    """Expand one complete HTML table, preserving blank/merged cell positions."""
    parser = _TableParser()
    parser.feed(text)
    parser.close()
    if (
        len(parser.tables) != 1
        or parser.table is not None
        or parser.cell is not None
        or parser.row is not None
    ):
        raise ValueError("Expected exactly one complete HTML table")
    rows = []
    pending = {}
    for source in parser.tables[0]:
        values = {c: text for c, (remaining, text) in pending.items()}
        following = {
            c: (remaining - 1, text) for c, (remaining, text) in pending.items() if remaining > 1
        }
        column = 0
        for cell in source:
            while column in values:
                column += 1
            for offset in range(cell["colspan"]):
                c = column + offset
                if c in values:
                    raise ValueError("Overlapping table spans")
                # A merged label belongs to its first column. Repeating it into
                # a control cell would fabricate assessments.
                value = cell["text"] if offset == 0 else ""
                values[c] = value
                if cell["rowspan"] > 1:
                    # Physical-cell evidence belongs to the printed top row;
                    # propagating a section's control down to its children is
                    # a curriculum interpretation, not OCR ground truth.
                    following[c] = (cell["rowspan"] - 1, "")
            column += cell["colspan"]
        rows.append([values.get(c, "") for c in range(max(values, default=-1) + 1)])
        pending = following
    if pending:
        raise ValueError("Table ends before rowspan")
    return rows


def map_chunk(table, chunk, page, geometry_rows):
    """Map strictly by supplied geometric row/column order, with no label lookup."""
    if len(table) != len(chunk["row_ids"]):
        raise ValueError(
            f"Row count mismatch: recognized {len(table)}, geometric {len(chunk['row_ids'])}"
        )
    mapping = {0: "discipline_code", 1: "discipline_name"}
    mapping.update({int(k): v for k, v in page["header_mapping"].items()})
    columns = max(mapping) + 1
    rows = []
    for values, row_id in zip(table, chunk["row_ids"]):
        if len(values) != columns:
            raise ValueError(
                f"Column count mismatch: recognized {len(values)}, geometric {columns}"
            )
        geom = geometry_rows[row_id]
        rows.append(
            {
                "prediction_id": row_id,
                "page": geom["page"],
                "bbox": geom["bbox"],
                "cells": {
                    key: {"text": values[col], "confidence": None} for col, key in mapping.items()
                },
            }
        )
    return rows


def _stop_tree(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
            timeout=10,
        )
    else:
        import signal

        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=10)


def _sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(args):
    """Launch a private llama.cpp CPU server, monitor RSS and persist raw results."""
    import psutil
    import requests

    manifest_path = args.manifest.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("gt_used") is not False:
        raise ValueError("Input must explicitly declare GT-free geometry")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    command = [
        str(args.server_bin),
        "-m",
        str(args.model),
        "--mmproj",
        str(args.mmproj),
        "-ngl",
        "0",
        "--no-mmproj-offload",
        "-t",
        str(args.threads),
        "-tb",
        str(args.threads),
        "-c",
        "4096",
        "-b",
        "128",
        "-ub",
        "128",
        "--parallel",
        "1",
        "--cache-ram",
        "0",
        "--no-cache-prompt",
        "--no-cache-idle-slots",
        "--host",
        "127.0.0.1",
        "--port",
        str(args.port),
    ]
    result = {
        "model": "ggml-org/GLM-OCR-GGUF:Q8_0",
        "source_sha256": manifest["source_sha256"],
        "gt_used": False,
        "prompt": PROMPT,
        "command": command,
        "model_sha256": _sha256(args.model),
        "mmproj_sha256": _sha256(args.mmproj),
        "rss_limit_bytes": args.max_rss_mb * 1024**2,
        "peak_rss_bytes": 0,
        "chunks": [],
        "rows": [],
        "errors": [],
    }
    finished = threading.Event()
    started = time.monotonic()
    environment = os.environ.copy()
    environment.update(
        OMP_NUM_THREADS=str(args.threads), OPENBLAS_NUM_THREADS="1", CUDA_VISIBLE_DEVICES=""
    )
    with (output / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=environment,
            **(
                {"creationflags": subprocess.CREATE_NO_WINDOW}
                if os.name == "nt"
                else {"start_new_session": True}
            ),
        )

        def monitor():
            while not finished.wait(0.1):
                try:
                    p = psutil.Process(process.pid)
                    rss = sum(
                        q.memory_info().rss
                        for q in [p, *p.children(recursive=True)]
                        if q.is_running()
                    )
                    result["peak_rss_bytes"] = max(result["peak_rss_bytes"], rss)
                    if rss > result["rss_limit_bytes"]:
                        result["errors"].append("rss_limit")
                        _stop_tree(process)
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    break

        watcher = threading.Thread(target=monitor, daemon=True)
        watcher.start()
        session = requests.Session()
        session.trust_env = False
        origin = f"http://127.0.0.1:{args.port}"
        try:
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"Server exited with {process.returncode}")
                if time.monotonic() - started > args.startup_timeout:
                    raise TimeoutError("Server startup timeout")
                try:
                    if session.get(origin + "/health", timeout=2).status_code == 200:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.2)
            result["startup_seconds"] = time.monotonic() - started
            geometry = {row["prediction_id"]: row for row in manifest["rows"]}
            chunks = [(p, c) for p in manifest["pages"] for c in p["chunks"]]
            if args.limit_chunks:
                chunks = chunks[: args.limit_chunks]
            for page, chunk in chunks:
                image_path = (manifest_path.parent / chunk["path"]).resolve()
                if (
                    not image_path.is_relative_to(manifest_path.parent)
                    or image_path.stat().st_size > MAX_IMAGE_BYTES
                ):
                    raise ValueError("Image path or size exceeds the benchmark boundary")
                raw = image_path.read_bytes()
                payload = {
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": "data:image/png;base64,"
                                        + base64.b64encode(raw).decode("ascii")
                                    },
                                },
                                {"type": "text", "text": PROMPT},
                            ],
                        }
                    ],
                    "temperature": 0,
                    "seed": 42,
                    "max_tokens": args.max_tokens,
                    "stream": False,
                }
                tick = time.monotonic()
                response = session.post(
                    origin + "/v1/chat/completions", json=payload, timeout=args.timeout
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                item = {
                    "path": chunk["path"],
                    "image_sha256": hashlib.sha256(raw).hexdigest(),
                    "seconds": time.monotonic() - tick,
                    "response": data,
                }
                try:
                    if data["choices"][0].get("finish_reason") != "stop":
                        raise ValueError("Model response did not finish normally")
                    mapped = map_chunk(parse_table(content), chunk, page, geometry)
                    result["rows"].extend(mapped)
                    item["mapped_rows"] = len(mapped)
                except ValueError as exc:
                    item["mapping_error"] = str(exc)
                result["chunks"].append(item)
                (output / "results.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(
                    json.dumps(
                        {
                            "chunk": chunk["path"],
                            "seconds": item["seconds"],
                            "mapped_rows": item.get("mapped_rows", 0),
                            "error": item.get("mapping_error"),
                        }
                    ),
                    flush=True,
                )
        except Exception as exc:
            result["errors"].append(f"{type(exc).__name__}: {exc}")
        finally:
            _stop_tree(process)
            finished.set()
            watcher.join(timeout=5)
            session.close()
            result["wall_seconds_including_startup"] = time.monotonic() - started
            result["server_exit_code"] = process.returncode
            (output / "results.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    return 1 if result["errors"] else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("server-bin", "model", "mmproj", "manifest", "output"):
        parser.add_argument("--" + flag, type=Path, required=True)
    parser.add_argument("--port", type=int, default=18978)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--max-rss-mb", type=int, default=3072)
    parser.add_argument("--startup-timeout", type=float, default=60)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--limit-chunks", type=int, default=0)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())

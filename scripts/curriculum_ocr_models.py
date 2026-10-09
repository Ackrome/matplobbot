"""Optional CPU recognizers for the GT-free curriculum cell benchmark.

Only explicit local model files are loaded. These adapters never receive GT,
discipline dictionaries or expected semesters, and are not production imports.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scripts.curriculum_ocr_onnx import (
    MAX_INPUT_WIDTH,
    MODEL_HEIGHT,
    _decode_ctc,
    _line_images,
    _normalized_input,
)

NUMERIC_ALPHABET = frozenset("0123456789,.;: /-–—")
MAX_MODEL_BYTES = 128 * 1024 * 1024
MAX_EASY_MODEL_BYTES = 256 * 1024 * 1024


def constrained_ctc(probabilities, alphabet, *, numeric=False):
    """CTC decode, optionally restricting labels to the known numeric field type.

    Original probabilities are retained: masking is not confidence calibration.
    The blank label always stays available; no answer-dependent replacement or
    string-level Cyrillic-to-digit substitution happens here.
    """
    if not numeric:
        return _decode_ctc(probabilities, alphabet)
    import numpy as np

    values = np.asarray(probabilities)
    # Validate the full tensor before masking, so a NaN in an excluded class is
    # not concealed and dimensions follow the base recognizer contract.
    _decode_ctc(values, alphabet)
    allowed = np.array([i == 0 or char in NUMERIC_ALPHABET for i, char in enumerate(alphabet)])
    masked = np.where(allowed[None, None, :], values, 0)
    return _decode_ctc(masked, alphabet)


class PaddleCellRecognizer:
    """Bounded PP-OCRv3/v5/v6 ONNX CPU recognizer with embedded CTC alphabet."""

    def __init__(self, model_path, *, family, numeric=False, controls_only=False):
        import onnxruntime as ort

        path = Path(model_path)
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_MODEL_BYTES:
            raise ValueError("Expected a local ONNX model no larger than 128 MiB.")
        # A decoding/preprocessing view of one checkpoint is still one vote.
        self.family = family.split("__", 1)[0]
        self.numeric = numeric
        self.controls_only = controls_only
        self.model_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        self.model_bytes = path.stat().st_size
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.enable_cpu_mem_arena = False
        options.log_severity_level = 3
        self.session = ort.InferenceSession(
            str(path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
        if (
            len(inputs) != 1
            or len(outputs) != 1
            or len(inputs[0].shape) != 4
            or inputs[0].type != "tensor(float)"
            or inputs[0].shape[1] != 3
        ):
            raise ValueError("Expected one float32 three-channel NCHW CTC input/output.")
        if isinstance(inputs[0].shape[2], int) and inputs[0].shape[2] != 48:
            raise ValueError("Only officially documented 48-pixel recognizers are supported.")
        characters = (
            self.session.get_modelmeta().custom_metadata_map.get("character", "").splitlines()
        )
        if not characters or len(characters) > 25000 or any(not c for c in characters):
            raise ValueError("Missing or invalid embedded recognition alphabet.")
        self.alphabet = ["", *characters, " "]
        if isinstance(outputs[0].shape[-1], int) and outputs[0].shape[-1] != len(self.alphabet):
            raise ValueError("Output classes do not match the embedded alphabet.")
        self.supports_russian = all(char in characters for char in "АБВГДабвгд")
        if not controls_only and not self.supports_russian:
            raise ValueError("This model has no Russian alphabet; use controls_only.")
        self.input_name, self.output_name = inputs[0].name, outputs[0].name
        self.runtime = f"onnxruntime {ort.__version__} CPUExecutionProvider"

    def read(self, graycell, *, psm=6, digits=False):
        started = time.perf_counter()
        if self.controls_only and not digits:
            return {
                "text": "",
                "confidence": 0,
                "family": self.family,
                "abstained": True,
                "error": "unsupported_russian_alphabet",
                "seconds": 0,
            }
        text, confidences, evidence = [], [], []
        for line in _line_images(graycell):
            values = self.session.run(
                [self.output_name], {self.input_name: _normalized_input(line)}
            )[0]
            unrestricted, unrestricted_scores = constrained_ctc(values, self.alphabet)
            raw, scores = constrained_ctc(values, self.alphabet, numeric=self.numeric and digits)
            evidence.append(
                {
                    "unrestricted_text": unrestricted,
                    "selected_text": raw,
                    "selected_token_probabilities": scores,
                    "unrestricted_token_probabilities": unrestricted_scores,
                }
            )
            if raw.strip():
                text.append(raw.strip())
                confidences.extend(scores)
        return {
            "text": " ".join(text),
            "confidence": 100 * sum(confidences) / len(confidences) if confidences else 0,
            "family": self.family,
            "seconds": time.perf_counter() - started,
            "numeric_restriction": self.numeric and digits,
            "cache_hit": False,
            "line_evidence": evidence,
        }


class EasyCellRecognizer:
    """EasyOCR Cyrillic generation 1/2, CPU, local weights and no detector download."""

    def __init__(self, model_directory, *, generation=2, numeric=False, threads=1):
        import easyocr
        import torch

        if generation not in (1, 2):
            raise ValueError("EasyOCR generation must be 1 or 2.")
        directory = Path(model_directory)
        path = directory / ("cyrillic.pth" if generation == 1 else "cyrillic_g2.pth")
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_EASY_MODEL_BYTES:
            raise ValueError("Expected a bounded local EasyOCR Cyrillic checkpoint.")
        self.family = f"easyocr_cyrillic_g{generation}"
        self.numeric = numeric
        self.model_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        self.model_bytes = path.stat().st_size
        torch.set_num_threads(threads)
        torch.set_num_interop_threads(1)
        self.reader = easyocr.Reader(
            ["ru", "en"],
            gpu=False,
            detector=False,
            model_storage_directory=str(directory),
            user_network_directory=str(directory / "network"),
            download_enabled=False,
            recog_network=f"cyrillic_g{generation}",
            quantize=True,
            verbose=False,
        )
        self.runtime = (
            f"easyocr {easyocr.__version__}; torch {torch.__version__}; CPU dynamic quantization"
        )

    def read(self, graycell, *, psm=6, digits=False):
        started = time.perf_counter()
        text, confidences = [], []
        for line in _line_images(graycell):
            # Match the ONNX adapter's aspect bound before EasyOCR rescales a
            # thin residual rule into a huge recurrent sequence.
            if math.ceil(MODEL_HEIGHT * line.shape[1] / line.shape[0]) > MAX_INPUT_WIDTH:
                raise ValueError("Text line exceeds the maximum normalized model width.")
            values = self.reader.recognize(
                line,
                decoder="greedy",
                detail=1,
                paragraph=False,
                allowlist="".join(sorted(NUMERIC_ALPHABET)) if self.numeric and digits else None,
                batch_size=1,
                workers=0,
            )
            for _, raw, confidence in values:
                if raw.strip():
                    text.append(raw.strip())
                    confidences.append(float(confidence))
        return {
            "text": " ".join(text),
            "confidence": 100 * sum(confidences) / len(confidences) if confidences else 0,
            "family": self.family,
            "seconds": time.perf_counter() - started,
            "numeric_restriction": self.numeric and digits,
            "cache_hit": False,
        }


def predict_dataset(manifest_path, engine, *, workers=2, preprocessing="clean", classify=True):
    """Read frozen image cells exported without GT; preserve physical row IDs."""
    manifest_path = Path(manifest_path)
    root = manifest_path.parent.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("gt_used") is not False or not 0 < len(manifest.get("rows", [])) <= 5000:
        raise ValueError("Expected an explicitly GT-free, bounded cell manifest.")
    rows, tasks = [], []
    for source in manifest["rows"]:
        row = {key: value for key, value in source.items() if key != "cells"}
        row["cells"] = {}
        rows.append(row)
        for field, cell in source["cells"].items():
            if cell["blank_gate"]:
                row["cells"][field] = {
                    "text": "",
                    "confidence": 0,
                    "family": engine.family,
                    "blank_gate": True,
                    "ink_fraction": cell["ink_fraction"],
                    "seconds": 0,
                }
            else:
                image_path = (
                    root / cell["raw_path" if preprocessing == "raw" else "clean_path"]
                ).resolve()
                if not image_path.is_relative_to(root):
                    raise ValueError("Cell image path escapes the dataset directory.")
                tasks.append((row, field, cell, image_path))

    import cv2

    progress = [0]
    progress_lock = threading.Lock()

    def recognize(task):
        row, field, cell, image_path = task
        image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError(f"Unreadable dataset image: {image_path}")
        if preprocessing == "otsu":
            image = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        try:
            reading = engine.read(image, digits=cell["numeric_field"])
        except (ValueError, TimeoutError) as exc:
            reading = {
                "text": "",
                "confidence": 0,
                "family": engine.family,
                "abstained": True,
                "error": f"{type(exc).__name__}: {exc}",
                "seconds": 0,
            }
        row["cells"][field] = dict(reading, ink_fraction=cell["ink_fraction"])
        with progress_lock:
            progress[0] += 1
            if progress[0] % 50 == 0 or progress[0] == len(tasks):
                print(f"{engine.family}: {progress[0]}/{len(tasks)} cell calls", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(recognize, tasks))
    if classify:
        from scripts.benchmark_curriculum_ocr import classify_rows

        rows = classify_rows(rows)
    return rows, manifest


def main(argv=None):
    """Run one explicitly selected local model; prediction input has no GT option."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf", type=Path)
    source.add_argument("--dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--family", required=True)
    parser.add_argument("--easyocr-generation", type=int, choices=(1, 2))
    parser.add_argument("--numeric", action="store_true")
    parser.add_argument("--controls-only", action="store_true")
    parser.add_argument(
        "--raw-rows",
        action="store_true",
        help="Dataset only: emit raw cells without importing production row classifiers.",
    )
    parser.add_argument("--package-path", action="append", default=[])
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--preprocessing", choices=("clean", "raw", "otsu"), default="clean")
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 8:
        parser.error("workers must be between 1 and 8")
    if args.raw_rows and not args.dataset:
        parser.error("raw-rows requires a frozen dataset")
    for package_path in args.package_path:
        sys.path.append(str(Path(package_path).resolve()))
    import psutil

    process = psutil.Process()
    peak_rss = [process.memory_info().rss]
    finished = threading.Event()

    def sample_memory():
        while not finished.wait(0.05):
            peak_rss[0] = max(peak_rss[0], process.memory_info().rss)

    monitor = threading.Thread(target=sample_memory, daemon=True)
    monitor.start()
    started = time.perf_counter()
    try:
        if args.easyocr_generation:
            engine = EasyCellRecognizer(
                args.model, generation=args.easyocr_generation, numeric=args.numeric, threads=1
            )
        else:
            engine = PaddleCellRecognizer(
                args.model,
                family=args.family,
                numeric=args.numeric,
                controls_only=args.controls_only,
            )
        initialized = time.perf_counter()
        args.output.mkdir(parents=True, exist_ok=True)
        if args.dataset:
            geometry_finished = initialized
            rows, manifest = predict_dataset(
                args.dataset,
                engine,
                preprocessing=args.preprocessing,
                workers=args.workers,
                classify=not args.raw_rows,
            )
            source_sha256 = manifest["source_sha256"]
        else:
            from scripts.benchmark_curriculum_ocr import detect_pages, predict

            pages = detect_pages(args.pdf, args.output)
            geometry_finished = time.perf_counter()
            rows = predict(pages, engine, preprocessing=args.preprocessing, workers=args.workers)
            source_sha256 = hashlib.sha256(args.pdf.read_bytes()).hexdigest()
        ended = time.perf_counter()
        peak_rss[0] = max(peak_rss[0], process.memory_info().rss)
        result = {
            "scenario": args.family,
            "rows": rows,
            "source_sha256": source_sha256,
            "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest()
            if args.dataset
            else None,
            "model_sha256": engine.model_sha256,
            "model_bytes": engine.model_bytes,
            "runtime": engine.runtime,
            "model_init_seconds": initialized - started,
            "geometry_seconds": geometry_finished - initialized,
            "inference_seconds": ended - geometry_finished,
            "total_seconds": ended - started,
            "peak_rss_mib": peak_rss[0] / 2**20,
            "workers": args.workers,
            "numeric_restriction": args.numeric,
            "controls_only": args.controls_only,
            "preprocessing": args.preprocessing,
            "rows_classified": not args.raw_rows,
            "cache_hits": 0,
            "evaluation_ground_truth_loaded": False,
        }
        target = args.output / f"{args.family}.json"
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps({k: v for k, v in result.items() if k != "rows"}, ensure_ascii=False),
            flush=True,
        )
    finally:
        finished.set()
        monitor.join(timeout=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

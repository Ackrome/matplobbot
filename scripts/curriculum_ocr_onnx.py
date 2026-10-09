"""Optional CPU-only PP-OCRv5 cell recognizer for offline curriculum benchmarks.

This is deliberately not imported by the production curriculum worker. The
caller supplies ruled-table cells and a locally downloaded, verified ONNX model.
No document identity, ground truth, course vocabulary or semester rules enter
recognition. PP-OCR/RapidOCR input normalization and CTC alphabet conventions
are documented in the colocated wiki.
"""

from __future__ import annotations

import hashlib
import math
import threading
import time
from pathlib import Path

MAX_MODEL_BYTES = 64 * 1024 * 1024
MAX_CELL_PIXELS = 1_000_000
MAX_CELL_EDGE = 4096
MAX_LINES = 12
MAX_INPUT_WIDTH = 2048
CELL_TIMEOUT_SECONDS = 10.0
MODEL_HEIGHT = 48
MIN_INPUT_WIDTH = 320
FAMILY = "ppocr_v5_eslav"


def _line_images(gray):
    """Find visual text lines by ink projection, without consulting OCR or GT."""
    import cv2
    import numpy as np

    if not isinstance(gray, np.ndarray) or gray.ndim != 2 or gray.dtype != np.uint8:
        raise ValueError("Expected a two-dimensional uint8 grayscale cell.")
    if not gray.size or gray.size > MAX_CELL_PIXELS or max(gray.shape) > MAX_CELL_EDGE:
        raise ValueError("Cell dimensions exceed the bounded benchmark input.")
    ink = gray < 200
    if np.count_nonzero(ink) / gray.size < 0.005:
        return []
    # Close short vertical gaps from letter dots/diacritics, but retain the
    # whitespace separating wrapped lines. The projection is independent of
    # content, model output, and the expected discipline name.
    active = (ink.sum(axis=1) >= max(1, round(gray.shape[1] * 0.003))).astype(np.uint8)
    active = cv2.morphologyEx(active[:, None], cv2.MORPH_CLOSE, np.ones((3, 1), np.uint8))[:, 0]
    indices = np.flatnonzero(active)
    if not len(indices):
        return []
    runs = []
    for y in indices:
        if runs and y == runs[-1][1]:
            runs[-1][1] = int(y) + 1
        else:
            runs.append([int(y), int(y) + 1])
    # A separated accent is a small adjacent fragment, not another text line.
    median_height = float(np.median([b - a for a, b in runs]))
    merged = []
    for a, b in runs:
        if (
            merged
            and a - merged[-1][1] <= max(2, round(median_height * 0.3))
            and (
                b - a <= max(3, median_height * 0.3)
                or merged[-1][1] - merged[-1][0] <= max(3, median_height * 0.3)
            )
        ):
            merged[-1][1] = b
        else:
            merged.append([a, b])
    if len(merged) > MAX_LINES:
        raise ValueError("Cell has too many visual text lines.")
    lines = []
    for top, bottom in merged:
        ys, xs = np.nonzero(ink[top:bottom])
        if len(xs) < 4:
            continue
        left, right = int(xs.min()), int(xs.max()) + 1
        if bottom - top < 2 or right - left < 2:
            continue
        pad = max(2, min(8, math.ceil((bottom - top) * 0.15)))
        line = gray[top:bottom, left:right]
        lines.append(cv2.copyMakeBorder(line, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255))
    return lines


def _normalized_input(gray, *, height=MODEL_HEIGHT):
    """PP-OCR's aspect-preserving CHW RGB normalization, with bounded width."""
    import cv2
    import numpy as np

    resized_width = max(1, math.ceil(height * gray.shape[1] / gray.shape[0]))
    if resized_width > MAX_INPUT_WIDTH:
        raise ValueError("Text line exceeds the maximum normalized model width.")
    width = max(MIN_INPUT_WIDTH, resized_width)
    pixels = cv2.resize(gray, (resized_width, height)).astype(np.float32) / 127.5 - 1.0
    tensor = np.zeros((1, 3, height, width), dtype=np.float32)
    tensor[0, :, :, :resized_width] = pixels
    return tensor


def _decode_ctc(prediction, alphabet):
    """Collapse adjacent CTC repeats, removing blanks but preserving raw text."""
    import numpy as np

    scores = np.asarray(prediction)
    if scores.ndim != 3 or scores.shape[0] != 1 or scores.shape[2] != len(alphabet):
        raise ValueError("Unexpected recognition tensor/alphabet dimensions.")
    if not np.all(np.isfinite(scores)) or np.any(scores < 0) or np.any(scores > 1.00001):
        raise ValueError("The expected model output must contain probabilities.")
    labels = scores[0].argmax(axis=1)
    chosen = []
    probabilities = []
    previous = None
    for position, label in enumerate(labels):
        label = int(label)
        if label and label != previous:
            chosen.append(alphabet[label])
            probabilities.append(float(scores[0, position, label]))
        previous = label
    return "".join(chosen), probabilities


class OnnxCellRecognizer:
    """Reusable, one-thread CPU session; recognize returns raw text and 0–100 confidence."""

    family = FAMILY

    def __init__(self, model_path):
        import onnxruntime as ort

        path = Path(model_path)
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_MODEL_BYTES:
            raise ValueError("Expected a bounded local ONNX model file.")
        self.model_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.enable_cpu_mem_arena = False
        options.log_severity_level = 3
        self.session = ort.InferenceSession(
            str(path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        inputs = self.session.get_inputs()
        outputs = self.session.get_outputs()
        if len(inputs) != 1 or len(inputs[0].shape) != 4 or inputs[0].type != "tensor(float)":
            raise ValueError("Expected one float NCHW recognition input.")
        if inputs[0].shape[1] != 3 or len(outputs) != 1:
            raise ValueError("Expected a three-channel single-output recognition model.")
        # PP-OCRv5's exported ONNX height is dynamic; its official rec_img_shape
        # is 3,48,320. Reject another fixed height rather than silently adapting
        # a different model while labeling it PP-OCRv5.
        if isinstance(inputs[0].shape[2], int) and inputs[0].shape[2] != MODEL_HEIGHT:
            raise ValueError("This adapter requires PP-OCRv5 recognition height 48.")
        characters = (
            self.session.get_modelmeta().custom_metadata_map.get("character", "").splitlines()
        )
        if not characters or len(characters) > 10000 or any(not c for c in characters):
            raise ValueError("The ONNX model must embed a valid character alphabet.")
        self.alphabet = ["", *characters, " "]
        classes = outputs[0].shape[-1]
        if isinstance(classes, int) and classes != len(self.alphabet):
            raise ValueError("Embedded alphabet does not match model output classes.")
        self.input_name = inputs[0].name
        self.output_name = outputs[0].name
        self._ort = ort

    def recognize(self, graycell):
        """Recognize one cell in reading order, abstaining on physically blank cells.

        A deadline requests cancellation through ONNX Runtime's RunOptions.
        This is not OS process isolation; run the full benchmark in a bounded
        process if a hard memory/time limit is required.
        """
        started = time.monotonic()
        lines = _line_images(graycell)
        text = []
        confidence = []
        for line in lines:
            remaining = CELL_TIMEOUT_SECONDS - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("OCR cell exceeded its time budget.")
            tensor = _normalized_input(line)
            options = self._ort.RunOptions()
            expired = threading.Event()

            def terminate(run_options=options, event=expired):
                event.set()
                run_options.terminate = True

            timer = threading.Timer(remaining, terminate)
            timer.daemon = True
            timer.start()
            try:
                output = self.session.run(
                    [self.output_name], {self.input_name: tensor}, run_options=options
                )[0]
            except Exception as exc:
                if expired.is_set():
                    raise TimeoutError("OCR cell exceeded its time budget.") from exc
                raise
            finally:
                timer.cancel()
            if expired.is_set():
                raise TimeoutError("OCR cell exceeded its time budget.")
            raw, scores = _decode_ctc(output, self.alphabet)
            if raw.strip():
                text.append(raw.strip())
                confidence.extend(scores)
        return {
            "text": " ".join(text),
            "confidence": round(100 * sum(confidence) / len(confidence), 4) if confidence else 0.0,
            "family": self.family,
            "seconds": round(time.monotonic() - started, 6),
        }

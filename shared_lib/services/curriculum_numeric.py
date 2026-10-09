"""Small CPU-only CTC recognizer for curriculum control cells.

The bundled model is trained on synthetic numeric strings only. It cannot read
course names, indices or headers and never receives curriculum ground truth.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

ALPHABET = "0123456789,-"
HEIGHT = 48
MAX_WIDTH = 384
MAX_PIXELS = 1_000_000
DEFAULT_MODEL = Path(__file__).resolve().parents[1] / "data" / "curriculum_numeric.onnx"


def prepare_cell(gray):
    """Normalize grayscale/geometry identically during synthesis and inference."""
    import cv2
    import numpy as np

    if not isinstance(gray, np.ndarray) or gray.ndim != 2 or gray.dtype != np.uint8:
        raise ValueError("Expected a two-dimensional uint8 grayscale cell.")
    if not gray.size or gray.size > MAX_PIXELS or max(gray.shape) > 4096:
        raise ValueError("Numeric cell exceeds the supported dimensions.")
    image = gray.copy()
    background = max(1.0, float(np.percentile(image, 85)))
    image = np.clip(image.astype(np.float32) * (255.0 / background), 0, 255).astype(np.uint8)
    # Remove only edge-like long narrow remnants; preserve comma-sized marks.
    mask = (image < 185).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    h, w = image.shape
    for index in range(1, count):
        x, y, cw, ch, area = stats[index]
        horizontal = cw >= w * 0.8 and ch <= max(2, h * 0.06) and (y <= 2 or y + ch >= h - 2)
        vertical = ch >= h * 0.85 and cw <= max(2, w * 0.06) and (x <= 2 or x + cw >= w - 2)
        if horizontal or vertical or area < 2:
            image[labels == index] = 255
    ink = image < 185
    ink_pixels = int(ink.sum())
    if ink_pixels < 3:
        return np.zeros((1, 1, HEIGHT, 32), dtype=np.float32), {
            "blank": True,
            "ink_pixels": ink_pixels,
        }
    ys, xs = np.nonzero(ink)
    left, right = max(0, int(xs.min()) - 3), min(w, int(xs.max()) + 4)
    top, bottom = max(0, int(ys.min()) - 3), min(h, int(ys.max()) + 4)
    crop = image[top:bottom, left:right]
    width = max(16, int(round(crop.shape[1] * (HEIGHT - 8) / crop.shape[0])))
    if width + 8 > MAX_WIDTH:
        raise ValueError("Numeric string is too wide; refusing aspect distortion.")
    pixels = cv2.resize(crop, (width, HEIGHT - 8), interpolation=cv2.INTER_AREA)
    width_padded = max(32, ((width + 8 + 3) // 4) * 4)
    canvas = np.full((HEIGHT, width_padded), 255, dtype=np.uint8)
    canvas[4 : HEIGHT - 4, 4 : width + 4] = pixels
    tensor = (1.0 - canvas.astype(np.float32) / 255.0)[None, None]
    return tensor, {"blank": False, "ink_pixels": ink_pixels, "normalized_width": width_padded}


def decode_ctc(probabilities):
    """Greedy CTC decode; blank=0 and adjacent repeats collapse only once."""
    import numpy as np

    probabilities = np.asarray(probabilities)
    if probabilities.ndim != 2 or probabilities.shape[1] != len(ALPHABET) + 1:
        raise ValueError("Unexpected numeric recognizer output shape.")
    if not np.isfinite(probabilities).all():
        raise ValueError("Numeric recognizer emitted non-finite values.")
    labels = probabilities.argmax(axis=1)
    tokens, confidence = [], []
    previous = 0
    for index, label in enumerate(labels):
        label = int(label)
        if label and label != previous:
            tokens.append(ALPHABET[label - 1])
            confidence.append(float(probabilities[index, label]))
        elif label and label == previous:
            confidence[-1] = max(confidence[-1], float(probabilities[index, label]))
        previous = label
    return "".join(tokens), (min(confidence) if confidence else float(probabilities[:, 0].mean()))


class NumericRecognizer:
    """Read a complete numeric cell using a single-threaded ONNX CPU session."""

    def __init__(self, model_path=None):
        import onnxruntime as ort

        path = Path(model_path) if model_path else DEFAULT_MODEL
        metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        if metadata.get("alphabet") != ALPHABET or metadata.get("synthetic_only") is not True:
            raise ValueError("Unsupported numeric model metadata.")
        if path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("Numeric model exceeds the bounded model size.")
        self.model_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        if self.model_sha256 != metadata.get("sha256"):
            raise ValueError("Numeric model hash does not match its metadata.")
        self.threshold = float(metadata["confidence_threshold"])
        self.metadata = metadata
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.enable_cpu_mem_arena = False
        self.session = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name

    def read(self, graycell):
        """Return raw text/confidence, or an explicit abstention for uncertainty."""
        import numpy as np

        started = time.monotonic()
        try:
            tensor, diagnostics = prepare_cell(graycell)
        except ValueError as exc:
            return {
                "text": "",
                "raw_text": "",
                "confidence": 0.0,
                "abstained": True,
                "reason": str(exc),
                "model_sha256": self.model_sha256,
            }
        if diagnostics["blank"]:
            return {
                "text": "",
                "raw_text": "",
                "confidence": 100.0,
                "abstained": False,
                "reason": "blank",
                "diagnostics": diagnostics,
                "model_sha256": self.model_sha256,
            }
        logits = self.session.run(None, {self.input_name: tensor})[0][0]
        exp = np.exp(logits - logits.max(axis=1, keepdims=True))
        raw, confidence = decode_ctc(exp / exp.sum(axis=1, keepdims=True))
        # Grammar validates a whole sequence; it never turns letters into digits
        # or splits an ambiguous '123' into invented semester values.
        valid = not raw or bool(re.fullmatch(r"[0-9]+(?:[,-][0-9]+)*|-", raw))
        reason = (
            "nonempty_unreadable"
            if not raw
            else "ok"
            if valid and confidence >= self.threshold
            else "low_confidence"
            if valid
            else "invalid_sequence"
        )
        return {
            "text": raw if reason == "ok" else "",
            "raw_text": raw,
            "confidence": 100.0 * confidence,
            "abstained": reason != "ok",
            "reason": reason,
            "diagnostics": diagnostics,
            "model_sha256": self.model_sha256,
            "seconds": time.monotonic() - started,
        }

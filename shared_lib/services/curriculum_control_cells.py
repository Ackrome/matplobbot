"""Geometric wrapping support around the single-line numeric CNN."""

import re


def numeric_lines(gray):
    """Find distinct ink baselines while retaining descenders/separators.

    Line splitting has no text/semester knowledge. Short punctuation-only bands
    are attached to their preceding baseline instead of becoming a new line.
    """
    import cv2
    import numpy as np

    if not isinstance(gray, np.ndarray) or gray.ndim != 2 or gray.dtype != np.uint8:
        return [gray]
    if not gray.size or gray.size > 1_000_000 or max(gray.shape) > 4096:
        return [gray]  # Let the recognizer return its explicit bounds error.
    normalized = np.clip(gray.astype(float) * 255 / max(1, np.percentile(gray, 85)), 0, 255)
    binary = (normalized < 185).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    height, width = gray.shape
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        edge = x <= 2 or y <= 2 or x + w >= width - 2 or y + h >= height - 2
        rule = edge and (w > width * 0.8 and h <= 2 or h > height * 0.85 and w <= 2)
        if area < 3 or rule:
            binary[labels == i] = 0
    ys = np.flatnonzero(binary.sum(axis=1))
    if not len(ys):
        return [gray]
    groups = []
    for y in ys:
        if not groups or y - groups[-1][-1] > 3:
            groups.append([int(y)])
        else:
            groups[-1].append(int(y))
    tallest = max(group[-1] - group[0] + 1 for group in groups)
    merged = []
    for group in groups:
        if merged and group[-1] - group[0] + 1 < tallest * 0.35:
            merged[-1].extend(group)
        else:
            merged.append(group)
    if len(merged) < 2 or len(merged) > 8:
        return [gray]
    # A single glyph broken by a scanner should not become two numeric lines.
    if any(group[-1] - group[0] + 1 < max(4, tallest * 0.45) for group in merged):
        return [gray]
    return [
        cv2.copyMakeBorder(
            gray[group[0] : group[-1] + 1], 6, 6, 4, 4, cv2.BORDER_CONSTANT, value=255
        )
        for group in merged
    ]


def read_control_cell(gray, recognizer):
    """Read wrapped cells without inventing a missing comma between lines."""
    lines = numeric_lines(gray)
    if len(lines) == 1:
        return recognizer.read(gray)
    readings = [recognizer.read(line) for line in lines]
    raw = [value.get("raw_text", value.get("text", "")) for value in readings]
    confidence = min(value.get("confidence", 0) for value in readings)
    threshold = getattr(recognizer, "threshold", 0.9) * 100
    trustworthy = all(value and re.fullmatch(r"[0-9,\-]+", value) for value in raw)
    # A trailing comma/range mark can be an invalid *line* yet a valid cell.
    # Only that grammar failure is recoverable; confidence/bounds errors are not.
    trustworthy = (
        trustworthy
        and all(
            not value.get("abstained") or value.get("reason") == "invalid_sequence"
            for value in readings
        )
        and confidence >= threshold
    )
    explicit_boundaries = all(
        left.endswith((",", "-")) or right.startswith((",", "-"))
        for left, right in zip(raw, raw[1:])
    )
    combined = "".join(raw)
    valid = bool(re.fullmatch(r"[0-9]+(?:[,-][0-9]+)*|-", combined))
    accepted = trustworthy and explicit_boundaries and valid
    return {
        "text": combined if accepted else "",
        "raw_text": "\n".join(raw),
        "confidence": confidence,
        "abstained": not accepted,
        "reason": "wrapped_sequence" if accepted else "ambiguous_wrapped_sequence",
        "model_sha256": getattr(recognizer, "model_sha256", None),
        "line_readings": readings,
        "line_count": len(lines),
        "seconds": sum(value.get("seconds", 0) for value in readings),
    }

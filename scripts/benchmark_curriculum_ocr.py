"""Reproducible CPU OCR experiments; GT is opened only after predictions exist.

This is an offline benchmark, not a production import path. Predictions retain
every detected row and empty cell. Model outputs are cached by image and engine
configuration, never by expected answer. See wiki_benchmark_curriculum_ocr.md.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from importlib.metadata import version as package_version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

KINDS = ("exam", "pass", "graded_pass", "coursework", "course_project")
FIELDS = ("discipline_code", "discipline_name") + KINDS
BENCHMARK_VERSION = "fa-cell-benchmark-3"
ANLS_REFERENCE = "https://openaccess.thecvf.com/content/WACV2022/supplemental/Mathew_InfographicVQA_WACV_2022_supplemental.pdf"


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


@lru_cache(maxsize=65536)
def edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1]


@lru_cache(maxsize=65536)
def similarity(left: str, right: str) -> float:
    left, right = normalized(left), normalized(right)
    return 1 - edit_distance(left, right) / max(1, len(left), len(right))


def anls(left: str, right: str) -> float:
    """ST-VQA ANLS component: normalized edit distance strictly below 0.5."""
    # Original metric lowercases but does not collapse/strip whitespace.
    left, right = str(left or "").lower(), str(right or "").lower()
    score = 1 - edit_distance(left, right) / max(1, len(left), len(right))
    return score if score > 0.5 else 0.0


def match_name(raw: str, names: list[str], *, minimum=0.90, margin=0.08) -> dict:
    """Conservative lexical suggestion; raw text is never overwritten."""
    unique = {normalized(name): name for name in names if normalized(name)}
    ranked = sorted(((similarity(raw, name), name) for name in unique.values()), reverse=True)
    best, choice = ranked[0] if ranked else (0.0, None)
    gap = best - (ranked[1][0] if len(ranked) > 1 else 0.0)
    accepted = bool(normalized(raw) and best >= minimum and gap >= margin)
    return {
        "raw": raw,
        "suggestion": choice if accepted else None,
        "accepted": accepted,
        "score": round(best, 6),
        "margin": round(gap, 6),
    }


def consensus(readings: list[dict], *, minimum_votes=2, field=None) -> dict:
    """Require distinct checkpoints, not multiple PSM views of one model.

    The legacy key ``family`` identifies a checkpoint group, not an independent
    architecture: fast and best are both Tesseract, unlike PP-OCR.
    """
    all_readings = readings
    readings = [reading for reading in readings if not reading.get("abstained")]
    if field == "discipline_name":
        candidates = []
        for reading in readings:
            raw = reading.get("text", "")
            neighbors = [r for r in readings if similarity(raw, r.get("text", "")) >= 0.95]
            voters = {r["family"] for r in neighbors}
            mean = sum(similarity(raw, r.get("text", "")) for r in neighbors) / max(
                1, len(neighbors)
            )
            candidates.append((len(voters), mean, reading.get("confidence", 0), raw, neighbors))
        chosen = max(candidates, key=lambda item: item[:4]) if candidates else (0, 0, 0, "", [])
        accepted = chosen[0] >= minimum_votes
        return {
            "text": chosen[3] if accepted else "",
            "abstained": not accepted,
            "confidence": chosen[2] if accepted else 0,
            "name_medoid_similarity": 0.95,
            "votes": chosen[0],
            "readings": all_readings,
        }
    family_votes: dict[str, set[str]] = {}
    representatives = {}

    def key(text):
        value = normalized(text)
        if field == "discipline_code":
            from shared_lib.services.curriculum_ocr import _code

            return _code(text) or value
        if field in KINDS:
            semesters = control_semesters(text)
            return ",".join(map(str, semesters)) if semesters is not None else None
        return value

    for reading in readings:
        value = key(reading.get("text", ""))
        family_votes.setdefault(reading["family"], set()).add(value)
        representatives.setdefault(value, reading.get("text", ""))
    # A family whose own configurations disagree does not cast a deciding vote.
    votes = Counter(
        next(iter(values))
        for values in family_votes.values()
        if len(values) == 1 and None not in values
    )
    ordered = votes.most_common()
    accepted = bool(
        ordered
        and ordered[0][1] >= minimum_votes
        and (len(ordered) == 1 or ordered[0][1] > ordered[1][1])
    )
    winner = ordered[0][0] if accepted else None
    return {
        "text": representatives[winner] if accepted else "",
        "abstained": not accepted,
        "confidence": min(
            (r.get("confidence", 0) for r in readings if key(r.get("text", "")) == winner),
            default=0,
        ),
        "votes": dict(votes),
        "family_votes": {k: sorted(v, key=lambda item: str(item)) for k, v in family_votes.items()},
        "readings": all_readings,
    }


def y_overlap(left: list[float], right: list[float]) -> float:
    overlap = max(0, min(left[3], right[3]) - max(left[1], right[1]))
    union = max(left[3], right[3]) - min(left[1], right[1])
    return overlap / max(union, 1e-9)


def align_rows(gt_rows: list[dict], predictions: list[dict], *, threshold=0.45):
    """One-to-one geometry alignment; never use labels or OCR to align rows."""
    edges = [
        (y_overlap(g["bbox"], p["bbox"]), i, j)
        for i, g in enumerate(gt_rows)
        for j, p in enumerate(predictions)
        if g["page"] == p["page"]
    ]
    used_gt, used_pred, matches = set(), set(), {}
    for score, i, j in sorted(edges, reverse=True):
        if score >= threshold and i not in used_gt and j not in used_pred:
            used_gt.add(i)
            used_pred.add(j)
            matches[i] = (j, score)
    return matches, set(range(len(predictions))) - used_pred


def control_semesters(value: str):
    from shared_lib.services.curriculum_documents import _semester_numbers

    return _semester_numbers(value, 9)


def evaluate(gt_rows: list[dict], predictions: list[dict]) -> tuple[dict, list[dict]]:
    matches, extra = align_rows(gt_rows, predictions)
    counts = Counter(
        {
            key: 0
            for key in (
                "row_classifier_tp",
                "row_classifier_fp",
                "row_classifier_fn",
                "row_classifier_tn",
                "row_classifier_missing",
                "row_classifier_missing_positive",
                "row_classifier_extra_positive",
                "row_classifier_extra_negative",
            )
        }
    )
    name_scores, name_errors, name_chars = [], 0, 0
    discipline_name_scores = []
    gt_facts, pred_facts, strict_code_facts, strict_identity_facts, errors = (
        set(),
        set(),
        set(),
        set(),
        [],
    )
    for i, truth in enumerate(gt_rows):
        counts["rows"] += 1
        j, overlap = matches.get(i, (None, 0.0))
        pred = predictions[j] if j is not None else {"cells": {}}
        from shared_lib.services.curriculum_ocr import _code

        correct_code = _code(pred["cells"].get("discipline_code", {}).get("text", "")) == _code(
            truth.get("discipline_code", "")
        )
        candidate_name = re.sub(
            r"\s+[=|_~]+$", "", pred["cells"].get("discipline_name", {}).get("text", "")
        ).strip()
        correct_name = normalized(candidate_name) == normalized(truth.get("discipline_name", ""))
        counts["matched_rows"] += j is not None
        differences = []
        expected_discipline = truth.get("row_type") == "discipline"
        classification_known = j is not None and isinstance(pred.get("is_discipline"), bool)
        if not classification_known:
            counts["row_classifier_missing"] += 1
            counts["row_classifier_missing_positive"] += expected_discipline
            differences.append(
                {
                    "field": "row_type",
                    "expected": truth.get("row_type"),
                    "predicted": "missing",
                    "abstained": True,
                }
            )
        else:
            actual_discipline = pred["is_discipline"]
            outcome = (
                ("tp" if actual_discipline else "fn")
                if expected_discipline
                else ("fp" if actual_discipline else "tn")
            )
            counts["row_classifier_" + outcome] += 1
            if actual_discipline != expected_discipline:
                differences.append(
                    {
                        "field": "row_type",
                        "expected": truth.get("row_type"),
                        "predicted": "discipline" if actual_discipline else "non_discipline",
                        "abstained": False,
                    }
                )
        for field in ("discipline_code", "discipline_name"):
            reading = pred["cells"].get(field, {})
            raw = reading.get("text", "")
            expected = truth.get(field, "")
            exact = (
                normalized(raw) == normalized(expected)
                and not reading.get("abstained")
                and j is not None
            )
            counts[field + "_exact"] += exact
            if not exact:
                differences.append(
                    {
                        "field": field,
                        "expected": expected,
                        "predicted": raw,
                        "abstained": bool(reading.get("abstained")),
                    }
                )
            if field == "discipline_name":
                name_scores.append(anls(expected, raw))
                name_errors += edit_distance(normalized(expected), normalized(raw))
                name_chars += len(normalized(expected))
                if truth.get("row_type") == "discipline":
                    counts["discipline_rows"] += 1
                    counts["discipline_name_exact_only"] += exact
                    discipline_name_scores.append(anls(expected, raw))
            elif truth.get("row_type") == "discipline":
                counts["discipline_code_canonical_exact"] += bool(
                    j is not None and _code(raw) == _code(expected)
                )
        for kind in KINDS:
            expected = truth.get("semesters", {}).get(kind, [])
            expected_raw = truth.get("controls", {}).get(kind, "")
            reading = pred["cells"].get(kind, {})
            raw = reading.get("text", "")
            actual = control_semesters(raw)
            accepted = j is not None and kind in pred["cells"] and not reading.get("abstained")
            raw_exact = accepted and normalized(raw) == normalized(expected_raw)
            # Section figures are counts, not semester numbers. Score those as
            # literal cells; only discipline rows have semester semantics.
            correct = (
                (accepted and actual == expected)
                if truth.get("row_type") == "discipline"
                else raw_exact
            )
            counts["control_cells"] += 1
            counts["control_cells_exact"] += correct
            counts["accepted_cells"] += accepted
            counts["control_raw_exact"] += raw_exact
            if truth.get("row_type") == "discipline":
                counts["discipline_control_cells"] += 1
                counts["discipline_control_cells_exact"] += correct
                if expected:
                    counts["discipline_nonblank_control_cells"] += 1
                    counts["discipline_nonblank_control_cells_exact"] += correct
            if not normalized(expected_raw):
                counts["blank_cells"] += 1
                counts["blank_false_positive"] += bool(accepted and normalized(raw))
                counts["blank_raw_ink_false_positive"] += bool(accepted and normalized(raw))
            else:
                counts["nonblank_cells"] += 1
                counts["nonblank_cells_exact"] += correct
            if not correct:
                differences.append(
                    {
                        "field": kind,
                        "expected": truth.get("controls", {}).get(kind, ""),
                        "expected_semesters": expected,
                        "predicted": raw,
                        "predicted_semesters": actual,
                        "abstained": not accepted,
                    }
                )
            if truth.get("row_type") == "discipline":
                gt_facts.update((truth["row_id"], kind, term) for term in expected)
            if accepted and pred.get("is_discipline"):
                pred_facts.update((truth["row_id"], kind, term) for term in (actual or []))
                code_id = truth["row_id"] if correct_code else "wrong_code_" + truth["row_id"]
                identity_id = (
                    truth["row_id"]
                    if correct_code and correct_name
                    else "wrong_identity_" + truth["row_id"]
                )
                strict_code_facts.update((code_id, kind, term) for term in (actual or []))
                strict_identity_facts.update((identity_id, kind, term) for term in (actual or []))
            if truth.get("row_type") == "discipline" and expected and not pred.get("is_discipline"):
                differences.append(
                    {
                        "field": kind,
                        "expected_semesters": expected,
                        "dropped_by_row_classifier": True,
                        "predicted": raw,
                    }
                )
        if differences:
            errors.append(
                {
                    "row_id": truth["row_id"],
                    "page": truth["page"],
                    "discipline_name": truth.get("discipline_name"),
                    "row_type": truth.get("row_type"),
                    "bbox": truth["bbox"],
                    "y_iou": round(overlap, 5),
                    "missing_row": j is None,
                    "differences": differences,
                }
            )
    for j in extra:
        pred = predictions[j]
        if pred.get("is_discipline"):
            counts["row_classifier_fp"] += 1
            counts["row_classifier_extra_positive"] += 1
            errors.append(
                {
                    "row_id": f"extra_{j}",
                    "page": pred["page"],
                    "bbox": pred["bbox"],
                    "row_type": None,
                    "discipline_name": pred["cells"].get("discipline_name", {}).get("text", ""),
                    "y_iou": 0.0,
                    "missing_row": False,
                    "differences": [
                        {"field": "row_type", "expected": "no_gt_row", "predicted": "discipline"}
                    ],
                }
            )
        else:
            counts["row_classifier_extra_negative"] += 1
        if pred.get("is_discipline"):
            for kind in KINDS:
                reading = pred["cells"].get(kind, {})
                if not reading.get("abstained"):
                    pred_facts.update(
                        (f"extra_{j}", kind, term)
                        for term in (control_semesters(reading.get("text", "")) or [])
                    )
                    strict_code_facts.update(
                        (f"extra_{j}", kind, term)
                        for term in (control_semesters(reading.get("text", "")) or [])
                    )
                    strict_identity_facts.update(
                        (f"extra_{j}", kind, term)
                        for term in (control_semesters(reading.get("text", "")) or [])
                    )
    tp, fp, fn = len(gt_facts & pred_facts), len(pred_facts - gt_facts), len(gt_facts - pred_facts)
    counts.update(
        facts_tp=tp,
        facts_fp=fp,
        facts_fn=fn,
        gt_facts=len(gt_facts),
        predicted_facts=len(pred_facts),
        extra_prediction_rows=len(extra),
        missing_rows=len(gt_rows) - len(matches),
    )
    metrics = dict(counts)
    for label, facts in (
        ("strict_code", strict_code_facts),
        ("strict_identity", strict_identity_facts),
    ):
        true_positive, false_positive, false_negative = (
            len(facts & gt_facts),
            len(facts - gt_facts),
            len(gt_facts - facts),
        )
        metrics.update(
            {
                f"{label}_tp": true_positive,
                f"{label}_fp": false_positive,
                f"{label}_fn": false_negative,
                f"{label}_precision": true_positive / max(1, true_positive + false_positive),
                f"{label}_recall": true_positive / max(1, true_positive + false_negative),
            }
        )
    metrics.update(
        name_anls=sum(name_scores) / max(1, len(name_scores)),
        name_cer=name_errors / max(1, name_chars),
        fact_precision=tp / max(1, tp + fp),
        fact_recall=tp / max(1, tp + fn),
        fact_f1=2 * tp / max(1, 2 * tp + fp + fn),
        control_accuracy=counts["control_cells_exact"] / max(1, counts["control_cells"]),
        nonblank_control_accuracy=counts["nonblank_cells_exact"] / max(1, counts["nonblank_cells"]),
        accepted_control_coverage=counts["accepted_cells"] / max(1, counts["control_cells"]),
        code_accuracy=counts["discipline_code_exact"] / max(1, len(gt_rows)),
        name_accuracy=counts["discipline_name_exact"] / max(1, len(gt_rows)),
    )
    # Keep all-row exact metrics distinct from discipline-only metrics.
    metrics["discipline_name_accuracy"] = counts["discipline_name_exact_only"] / max(
        1, counts["discipline_rows"]
    )
    metrics["discipline_name_anls"] = sum(discipline_name_scores) / max(
        1, len(discipline_name_scores)
    )
    metrics["discipline_code_canonical_accuracy"] = counts["discipline_code_canonical_exact"] / max(
        1, counts["discipline_rows"]
    )
    metrics["discipline_control_accuracy"] = counts["discipline_control_cells_exact"] / max(
        1, counts["discipline_control_cells"]
    )
    metrics["discipline_nonblank_control_accuracy"] = counts[
        "discipline_nonblank_control_cells_exact"
    ] / max(1, counts["discipline_nonblank_control_cells"])
    metrics["row_classifier_recall_with_missing"] = counts["row_classifier_tp"] / max(
        1,
        counts["row_classifier_tp"]
        + counts["row_classifier_fn"]
        + counts["row_classifier_missing_positive"],
    )
    errors.sort(
        key=lambda row: (
            sum(d["field"] in KINDS for d in row["differences"]),
            len(row["differences"]),
        ),
        reverse=True,
    )
    return metrics, errors


def evaluate_dictionary(gt_rows, predictions, names, *, minimum, margin):
    matches, _ = align_rows(gt_rows, predictions)
    counts = Counter()
    vocabulary = {normalized(name) for name in names}
    for i, truth in enumerate(gt_rows):
        if truth.get("row_type") != "discipline":
            continue
        counts["disciplines"] += 1
        expected = normalized(truth["discipline_name"])
        counts["in_dictionary"] += expected in vocabulary
        raw = (
            predictions[matches[i][0]]["cells"]["discipline_name"].get("text", "")
            if i in matches
            else ""
        )
        correction = match_name(raw, names, minimum=minimum, margin=margin)
        if correction["accepted"]:
            counts["accepted"] += 1
            right = normalized(correction["suggestion"]) == expected
            counts["accepted_correct"] += right
            counts["accepted_wrong"] += not right
            counts["fixed"] += right and normalized(raw) != expected
            counts["hurt"] += not right and normalized(raw) == expected
        final = correction["suggestion"] if correction["accepted"] else raw
        counts["final_correct"] += normalized(final) == expected
    for key in (
        "disciplines",
        "in_dictionary",
        "accepted",
        "accepted_correct",
        "accepted_wrong",
        "fixed",
        "hurt",
        "final_correct",
    ):
        counts.setdefault(key, 0)
    return dict(
        counts,
        minimum_similarity=minimum,
        minimum_margin=margin,
        final_accuracy=counts["final_correct"] / max(1, counts["disciplines"]),
    )


def deskew_bbox_to_original(bbox, geometry):
    """Invert OpenCV's center rotation for all four normalized box corners."""
    width, height = geometry["width"], geometry["height"]
    if width <= 0 or height <= 0:
        raise ValueError("Invalid saved render geometry")
    angle = math.radians(geometry["deskew_degrees"])
    cosine, sine = math.cos(angle), math.sin(angle)
    points = []
    for x, y in ((bbox[0], bbox[1]), (bbox[2], bbox[1]), (bbox[2], bbox[3]), (bbox[0], bbox[3])):
        dx, dy = (x - 0.5) * width, (y - 0.5) * height
        points.append(
            ((cosine * dx - sine * dy) / width + 0.5, (sine * dx + cosine * dy) / height + 0.5)
        )
    return [
        min(p[0] for p in points),
        min(p[1] for p in points),
        max(p[0] for p in points),
        max(p[1] for p in points),
    ]


def evaluate_candidates(gt_rows, candidates, geometry_by_page=None):
    """Score the exact stock parser output separately from its raw-cell proxy."""
    from shared_lib.services.curriculum_ocr import _code

    truth_facts = {
        (row["row_id"], kind, semester)
        for row in gt_rows
        if row["row_type"] == "discipline"
        for kind, semesters in row["semesters"].items()
        for semester in semesters
    }
    predictions = {"geometry": set(), "strict_code": set(), "strict_identity": set()}
    errors, alignments = [], []
    for number, candidate in enumerate(candidates):
        raw_bbox = candidate.get("ocr", {}).get("bbox", [0, 0, 0, 0])
        geometry = (geometry_by_page or {}).get(candidate["page"])
        if geometry is None and candidate.get("ocr", {}).get("deskew_degrees", 0):
            raise ValueError(
                "Saved page geometry is required to align deskewed production candidates"
            )
        bbox = deskew_bbox_to_original(raw_bbox, geometry) if geometry is not None else raw_bbox
        matches = [
            (y_overlap(bbox, row["bbox"]), row)
            for row in gt_rows
            if row["page"] == candidate["page"]
        ]
        overlap, row = max(matches, key=lambda item: item[0]) if matches else (0, None)
        match = row if overlap >= 0.45 else None
        alignments.append(
            {
                "candidate_index": number,
                "page": candidate["page"],
                "bbox_deskewed": raw_bbox,
                "bbox_original": bbox,
                "y_iou": overlap,
                "gt_row_id": match["row_id"] if match else None,
            }
        )
        kind, semester = candidate["kind"], candidate["semester"]
        row_id = match["row_id"] if match else f"extra_{number}"
        code_right = bool(
            match and _code(candidate["discipline_code"]) == _code(match["discipline_code"])
        )
        name_right = bool(
            match
            and normalized(candidate["discipline_name"]) == normalized(match["discipline_name"])
        )
        predictions["geometry"].add((row_id, kind, semester))
        predictions["strict_code"].add(
            (row_id if code_right else "wrong_code_" + row_id, kind, semester)
        )
        predictions["strict_identity"].add(
            (row_id if code_right and name_right else "wrong_identity_" + row_id, kind, semester)
        )
        if not code_right or not name_right or (row_id, kind, semester) not in truth_facts:
            errors.append(
                {
                    "candidate": candidate,
                    "gt_row_id": match["row_id"] if match else None,
                    "expected_code": match["discipline_code"] if match else None,
                    "expected_name": match["discipline_name"] if match else None,
                    "code_correct": code_right,
                    "name_correct": name_right,
                }
            )
    scores = {}
    for label, facts in predictions.items():
        tp, fp, fn = len(facts & truth_facts), len(facts - truth_facts), len(truth_facts - facts)
        scores[label] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": tp / max(1, tp + fp),
            "recall": tp / max(1, tp + fn),
            "missing_facts": sorted(truth_facts - facts),
        }
    return {
        "candidate_count": len(candidates),
        "gt_fact_count": len(truth_facts),
        "scores": scores,
        "errors": errors,
        "bbox_method": "inverse saved per-page OpenCV deskew affine before original-page GT alignment",
        "candidate_alignments": alignments,
    }


def _json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


class CellEngine:
    def __init__(self, executable: Path, model: Path, family: str, cache: Path):
        self.executable, self.model, self.family, self.cache = executable, model, family, cache
        self.fingerprint = {
            lang: hashlib.sha256((model / f"{lang}.traineddata").read_bytes()).hexdigest()
            for lang in ("rus", "eng")
        }
        self.version = (
            subprocess.run([str(executable), "--version"], capture_output=True, check=True)
            .stdout.decode()
            .splitlines()[0]
        )

    def read(self, image, *, psm=6, digits=False) -> dict:
        import cv2

        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            raise ValueError("PNG encoding failed")
        image_bytes = encoded.tobytes()
        config = {
            "version": self.version,
            "models": self.fingerprint,
            "psm": psm,
            "digits": digits,
            "family": self.family,
            "benchmark": BENCHMARK_VERSION,
        }
        digest = hashlib.sha256(
            image_bytes + json.dumps(config, sort_keys=True).encode()
        ).hexdigest()
        target = self.cache / (digest + ".json")
        if target.exists():
            return dict(json.loads(target.read_text(encoding="utf-8")), cache_hit=True)
        self.cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="mpb-cell-benchmark-") as folder:
            source = Path(folder) / "cell.png"
            source.write_bytes(image_bytes)
            command = [
                str(self.executable),
                str(source),
                "stdout",
                "--tessdata-dir",
                str(self.model),
                "-l",
                "rus+eng",
                "--psm",
                str(psm),
                "--oem",
                "1",
            ]
            if digits:
                command.extend(["-c", "tessedit_char_whitelist=0123456789,;-"])
            # Model-only folders do not contain Tesseract's configs/tsv file.
            # Set its actual parameter instead of silently accepting plain text.
            command.extend(["-c", "tessedit_create_tsv=1"])
            started = time.perf_counter()
            response = subprocess.run(
                command,
                capture_output=True,
                check=True,
                timeout=30,
                env=dict(os.environ, OMP_THREAD_LIMIT="1", OMP_NUM_THREADS="1"),
            )
            duration = time.perf_counter() - started
        words = parse_tesseract_tsv(response.stdout.decode("utf-8"))
        result = {
            "text": " ".join(row["text"].strip() for row in words),
            "confidence": min((max(0, float(row["conf"])) for row in words), default=0),
            "family": self.family,
            "seconds": duration,
            "cache_hit": False,
            "config": config,
            "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
        }
        _json(target, result)
        return result


def parse_tesseract_tsv(output: str) -> list[dict]:
    """Read literal OCR quote characters; TSV is not an Excel quoted dialect."""
    if not output.startswith("level\tpage_num\t"):
        raise RuntimeError("Tesseract did not return TSV; engine configuration is invalid")
    return [
        row
        for row in csv.DictReader(io.StringIO(output), delimiter="\t", quoting=csv.QUOTE_NONE)
        if row.get("level") == "5" and row.get("text", "").strip()
    ]


class OnnxEngine:
    def __init__(self, model: Path, cache: Path):
        from scripts.curriculum_ocr_onnx import OnnxCellRecognizer

        self.recognizer = OnnxCellRecognizer(model)
        runtime_version = package_version("onnxruntime")
        self.fingerprint = {
            "onnx_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
            "adapter_sha256": hashlib.sha256(
                (ROOT / "scripts/curriculum_ocr_onnx.py").read_bytes()
            ).hexdigest(),
            "onnxruntime_version": runtime_version,
        }
        self.family, self.version, self.cache = (
            "ppocr_v5_eslav",
            f"onnxruntime-cpu {runtime_version}",
            cache,
        )

    def read(self, image, *, psm=6, digits=False):
        import cv2

        encoded = cv2.imencode(".png", image)[1].tobytes()
        digest = hashlib.sha256(
            encoded
            + json.dumps(self.fingerprint, sort_keys=True).encode()
            + BENCHMARK_VERSION.encode()
        ).hexdigest()
        target = self.cache / (digest + ".json")
        if target.exists():
            return dict(json.loads(target.read_text(encoding="utf-8")), cache_hit=True)
        started = time.perf_counter()
        value = self.recognizer.recognize(image)
        result = dict(
            value,
            family=self.family,
            seconds=time.perf_counter() - started,
            cache_hit=False,
            image_sha256=hashlib.sha256(encoded).hexdigest(),
            config=self.fingerprint,
        )
        _json(target, result)
        return result


def detect_pages(pdf: Path, output: Path, *, deskew=True):
    """Render and infer lines/headers without opening the GT annotation files."""
    import cv2
    import numpy as np
    import pypdfium2

    from shared_lib.services.curriculum_ocr import _deskew, _grid, _header_mapping

    pages = []
    with pypdfium2.PdfDocument(pdf) as document:
        for number in range(1, len(document) + 1):
            page = document[number - 1]
            width, height = page.get_size()
            scale = min(5, 6000 / max(width, height), math.sqrt(24_000_000 / (width * height)))
            bitmap = page.render(scale=scale, grayscale=True)
            original = np.asarray(bitmap.to_pil()).copy()
            bitmap.close()
            page.close()
            image, angle = _deskew(original) if deskew else (original, 0.0)
            xs, ys, clean = _grid(image)
            header = next(
                (
                    i
                    for i in range(min(4, len(ys) - 1))
                    if ys[i + 1] - ys[i] > image.shape[0] * 0.07
                ),
                None,
            )
            if len(xs) < 6 or len(ys) < 4:
                mapping, error = {}, "No reliable ruled grid"
            elif header is None:
                mapping, error = {}, "No header geometry"
            else:
                mapping, error = _header_mapping(clean, xs, ys[max(0, header - 1)], ys[header + 1])
            bounds = (
                []
                if error
                else [(a, b) for a, b in zip(ys[header + 1 :], ys[header + 2 :]) if b - a >= 12]
            )
            inverse = cv2.invertAffineTransform(
                cv2.getRotationMatrix2D((image.shape[1] / 2, image.shape[0] / 2), angle, 1)
            )
            rows = []
            for i, (top, bottom) in enumerate(bounds):
                right = xs[max(mapping) + 1]
                points = (
                    np.array(
                        [[xs[0], top, 1], [right, top, 1], [right, bottom, 1], [xs[0], bottom, 1]]
                    )
                    @ inverse.T
                )
                bbox = [
                    float(points[:, 0].min() / image.shape[1]),
                    float(points[:, 1].min() / image.shape[0]),
                    float(points[:, 0].max() / image.shape[1]),
                    float(points[:, 1].max() / image.shape[0]),
                ]
                rows.append(
                    {
                        "prediction_id": f"p{number}_r{i + 1:03d}",
                        "page": number,
                        "bbox": bbox,
                        "pixel_bounds": [xs[0], top, right, bottom],
                        "top": top,
                        "bottom": bottom,
                    }
                )
            metadata = {
                "page": number,
                "width": image.shape[1],
                "height": image.shape[0],
                "render_scale": scale,
                "deskew_degrees": angle,
                "xs": xs,
                "ys": ys,
                "header_mapping": mapping,
                "header_error": error,
                "rows": rows,
            }
            _json(output / f"geometry-{'deskew' if deskew else 'raw'}-page{number}.json", metadata)
            pages.append(dict(metadata, raw=image, clean=clean))
    return pages


def _crop(page, row, column, preprocessing):
    import cv2

    image = page["raw" if preprocessing == "raw" else "clean"]
    a, b = row["top"], row["bottom"]
    x0, x1 = page["xs"][column : column + 2]
    cell = image[a + 4 : b - 3, x0 + 4 : x1 - 3].copy()
    if preprocessing == "otsu":
        cell = cv2.threshold(cell, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    scale = min(3, max(1, 42 / max(cell.shape[0], 1)))
    cell = cv2.resize(
        cell,
        (max(1, int(cell.shape[1] * scale)), max(1, int(cell.shape[0] * scale))),
        interpolation=cv2.INTER_CUBIC,
    )
    return cv2.copyMakeBorder(cell, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)


def classify_rows(rows):
    from shared_lib.services.curriculum_documents import _SECTION
    from shared_lib.services.curriculum_ocr import _code

    all_codes = {_code(row["cells"]["discipline_code"].get("text", "")) for row in rows} - {None}
    for row in rows:
        code = _code(row["cells"]["discipline_code"].get("text", ""))
        name = row["cells"]["discipline_name"].get("text", "")
        row["is_discipline"] = bool(
            code
            and name
            and not _SECTION.match(name)
            and not any(other.startswith(code + ".") for other in all_codes)
        )
    return rows


def predict(pages, engine: CellEngine, *, psm=6, preprocessing="clean", workers=2, batched=False):
    from shared_lib.services.curriculum_ocr import _batch_cells

    rows, tasks = [], []
    for page in pages:
        mapping = {0: "discipline_code", 1: "discipline_name", **page["header_mapping"]}
        local = [dict(row, cells={}) for row in page["rows"]]
        rows.extend(local)
        for column, field in mapping.items():
            if batched:
                # Strip the per-cell padding because the production batcher adds its own.
                cells = [
                    page["clean"][
                        row["top"] + 4 : row["bottom"] - 3,
                        page["xs"][column] + 4 : page["xs"][column + 1] - 3,
                    ]
                    for row in local
                ]
                values = _batch_cells(cells, digits=field in KINDS)
                for row, value, cell in zip(local, values, cells):
                    ink = float((cell < 175).sum()) / max(1, cell.size)
                    if field in KINDS and ink < 0.005:
                        value = dict(value, text="", blank_gate=True)
                    row["cells"][field] = dict(value, family=engine.family, ink_fraction=ink)
                continue
            for row in local:
                cell = _crop(page, row, column, preprocessing)
                # The gate examines the rule-cleaned unscaled cell for every variant.
                gate_cell = page["clean"][
                    row["top"] + 4 : row["bottom"] - 3,
                    page["xs"][column] + 4 : page["xs"][column + 1] - 3,
                ]
                ink = float((gate_cell < 175).sum()) / max(1, gate_cell.size)
                if field in KINDS and ink < 0.005:
                    row["cells"][field] = {
                        "text": "",
                        "confidence": 0,
                        "family": engine.family,
                        "blank_gate": True,
                        "ink_fraction": ink,
                        "seconds": 0,
                    }
                else:
                    tasks.append((row, field, cell, ink))

    def recognize(task):
        row, field, cell, ink = task
        try:
            value = engine.read(cell, psm=psm, digits=field in KINDS)
        except (ValueError, TimeoutError, subprocess.TimeoutExpired) as exc:
            value = {
                "text": "",
                "confidence": 0,
                "family": engine.family,
                "abstained": True,
                "error": f"{type(exc).__name__}: {exc}",
                "seconds": 0,
                "cache_hit": False,
                "cell_shape": list(cell.shape),
            }
        row["cells"][field] = dict(value, ink_fraction=ink)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(recognize, tasks))
    return classify_rows(rows)


def ensemble(scenarios: list[dict], *, semantic=False) -> list[dict]:
    by_scenario = [
        {(r["page"], r["prediction_id"]): r for r in scenario["rows"]} for scenario in scenarios
    ]
    rows = []
    for key, first in by_scenario[0].items():
        row = {
            key_: value for key_, value in first.items() if key_ not in {"cells", "is_discipline"}
        }
        row["cells"] = {
            field: consensus(
                [
                    index[key]["cells"].get(
                        field,
                        {
                            "text": "",
                            "family": str(i),
                            "abstained": True,
                            "error": "missing_column_header",
                        },
                    )
                    for i, index in enumerate(by_scenario)
                    if key in index
                ],
                field=field if semantic else None,
            )
            for field in FIELDS
        }
        rows.append(row)
    return classify_rows(rows)


def hybrid_fields_development(scenarios: dict[str, dict]) -> list[dict]:
    """Fixed field routing without GT: best codes, baseline names, ONNX controls.

    This development hypothesis was selected after aggregate results on this
    same GT. It is not a held-out result or a production recommendation.
    """
    sources = {
        "discipline_code": "best_clean6",
        "discipline_name": "baseline",
        **{kind: "onnx_clean" for kind in KINDS},
    }
    indices = {
        name: {(r["page"], r["prediction_id"]): r for r in scenarios[name]["rows"]}
        for name in set(sources.values())
    }
    rows = []
    for key, first in indices["baseline"].items():
        row = {
            field: value
            for field, value in first.items()
            if field not in {"cells", "is_discipline"}
        }
        row["cells"] = {}
        for field, name in sources.items():
            reading = indices[name].get(key, {}).get("cells", {}).get(field)
            row["cells"][field] = dict(
                reading
                or {"text": "", "confidence": 0, "abstained": True, "error": "missing_source_cell"},
                source_scenario=name,
            )
        rows.append(row)
    return classify_rows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tesseract", type=Path, required=True)
    parser.add_argument("--fast-model", type=Path, required=True)
    parser.add_argument("--best-model", type=Path)
    parser.add_argument("--onnx-model", type=Path)
    parser.add_argument("--gt", type=Path, nargs="*")
    parser.add_argument("--dictionary", type=Path, help="Independent JSON list of course names")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument(
        "--scenarios",
        default="baseline,fast_clean6,fast_clean7,fast_raw6,fast_otsu6,fast_nodeskew6,best_clean6,best_clean7,onnx_clean,ensemble2,ensemble4,ensemble3,ensemble3_semantic,hybrid_fields_development",
    )
    parser.add_argument("--evaluate-only", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 8:
        parser.error("workers must be 1..8")
    args.output.mkdir(parents=True, exist_ok=True)
    source_hash = hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    requested = args.scenarios.split(",")
    results = {}
    if not args.evaluate_only:
        os.environ["CURRICULUM_TESSERACT_CMD"] = str(args.tesseract)
        os.environ["TESSDATA_PREFIX"] = str(args.fast_model)
        os.environ["OMP_THREAD_LIMIT"] = "1"
        import cv2

        cv2.setNumThreads(1)
        engines = {
            "fast": CellEngine(
                args.tesseract, args.fast_model, "tessdata_fast_4.1.0", args.output / "cache"
            )
        }
        if args.best_model:
            engines["best"] = CellEngine(
                args.tesseract, args.best_model, "tessdata_best_4.1.0", args.output / "cache"
            )
        if args.onnx_model:
            engines["onnx"] = OnnxEngine(args.onnx_model, args.output / "cache")
        geometry_started = time.perf_counter()
        pages = detect_pages(args.pdf, args.output)
        geometry_seconds = time.perf_counter() - geometry_started
        raw_pages, raw_geometry_seconds = None, None
        for name in requested:
            if name == "hybrid_fields_development":
                continue
            target = args.output / f"predictions-{name}.json"
            if name.startswith("ensemble"):
                members = (
                    ["fast_clean6", "best_clean6", "onnx_clean"]
                    if name.startswith("ensemble3")
                    else ["fast_clean6", "best_clean6"]
                    if name == "ensemble2"
                    else ["fast_clean6", "fast_clean7", "best_clean6", "best_clean7"]
                )
                for member in members:
                    existing = args.output / f"predictions-{member}.json"
                    if member not in results and existing.exists():
                        saved = json.loads(existing.read_text(encoding="utf-8"))
                        if (
                            saved.get("source_sha256") == source_hash
                            and saved.get("benchmark_version") == BENCHMARK_VERSION
                        ):
                            results[member] = saved
                if not all(member in results for member in members):
                    continue
                started = time.perf_counter()
                rows = ensemble(
                    [results[member] for member in members], semantic=name.endswith("_semantic")
                )
                result = {
                    "scenario": name,
                    "rows": rows,
                    "members": members,
                    "model_count": 3 if name.startswith("ensemble3") else 2,
                    "architecture_count": 2 if name.startswith("ensemble3") else 1,
                    "semantic_normalization": name.endswith("_semantic"),
                    "benchmark_version": BENCHMARK_VERSION,
                    "inference_seconds": sum(
                        results[member]["inference_seconds"] for member in members
                    ),
                    "fusion_seconds": time.perf_counter() - started,
                    "source_sha256": source_hash,
                }
                result["pipeline_seconds"] = (
                    result["inference_seconds"] + geometry_seconds + result["fusion_seconds"]
                )
            else:
                family = (
                    "onnx"
                    if name.startswith("onnx")
                    else "best"
                    if name.startswith("best")
                    else "fast"
                )
                if family not in engines:
                    continue
                preprocessing = "raw" if "raw" in name else "otsu" if "otsu" in name else "clean"
                psm = 7 if name.endswith("7") else 6
                if "nodeskew" in name and raw_pages is None:
                    raw_geometry_started = time.perf_counter()
                    raw_pages = detect_pages(args.pdf, args.output, deskew=False)
                    raw_geometry_seconds = time.perf_counter() - raw_geometry_started
                started = time.perf_counter()
                # Isolate scenarios so shared cell pixels cannot make a raw-vs-
                # clean ablation appear faster by inheriting another run's cache.
                engines[family].cache = args.output / "cache" / name
                rows = predict(
                    raw_pages if "nodeskew" in name else pages,
                    engines[family],
                    psm=psm,
                    preprocessing=preprocessing,
                    workers=args.workers,
                    batched=name == "baseline",
                )
                result = {
                    "scenario": name,
                    "rows": rows,
                    "source_sha256": source_hash,
                    "inference_seconds": time.perf_counter() - started,
                    "geometry_seconds": raw_geometry_seconds
                    if "nodeskew" in name
                    else geometry_seconds,
                    "model": engines[family].fingerprint,
                    "engine_version": engines[family].version,
                    "psm": psm,
                    "preprocessing": preprocessing,
                    "deskew": "nodeskew" not in name,
                    "batched": name == "baseline",
                    "workers": args.workers,
                    "benchmark_version": BENCHMARK_VERSION,
                }
                calls = [
                    cell for row in rows for cell in row["cells"].values() if "cache_hit" in cell
                ]
                hits = sum(bool(cell["cache_hit"]) for cell in calls)
                result["timing"] = {
                    "cache_hits": hits,
                    "ocr_calls": len(calls),
                    "kind": "cold" if not hits else "warm" if hits == len(calls) else "mixed",
                    "original_call_seconds_sum": sum(cell.get("seconds", 0) for cell in calls),
                    "wall_seconds": result["inference_seconds"],
                    "workers": args.workers,
                }
                result["pipeline_seconds"] = (
                    result["inference_seconds"] + result["geometry_seconds"]
                )
            results[name] = result
            _json(target, result)
            print(
                f"{name}: {len(result['rows'])} rows, {result['inference_seconds']:.2f}s",
                flush=True,
            )
        from shared_lib.services.curriculum_ocr import (
            parse_scanned_curriculum_legacy as parse_scanned_curriculum,
        )

        started = time.perf_counter()
        production = parse_scanned_curriculum(args.pdf.read_bytes())
        for assessment in production.get("assessments", []):
            assessment.get("ocr", {}).pop("crop_png_base64", None)
        production["inference_seconds"] = time.perf_counter() - started
        production["source_sha256"] = source_hash
        _json(args.output / "production-candidates.json", production)
    else:
        for name in requested:
            target = args.output / f"predictions-{name}.json"
            if target.exists():
                results[name] = json.loads(target.read_text(encoding="utf-8"))
                if results[name]["source_sha256"] != source_hash:
                    raise ValueError("Prediction source hash differs from PDF")
    if "hybrid_fields_development" in requested and not (
        args.evaluate_only and "hybrid_fields_development" in results
    ):
        members = ["baseline", "best_clean6", "onnx_clean"]
        for member in members:
            path = args.output / f"predictions-{member}.json"
            if member not in results and path.exists():
                saved = json.loads(path.read_text(encoding="utf-8"))
                if (
                    saved.get("source_sha256") == source_hash
                    and saved.get("benchmark_version") == BENCHMARK_VERSION
                ):
                    results[member] = saved
        if all(member in results for member in members):
            started = time.perf_counter()
            rows = hybrid_fields_development(results)
            result = {
                "scenario": "hybrid_fields_development",
                "rows": rows,
                "members": members,
                "model_count": 3,
                "architecture_count": 2,
                "source_sha256": source_hash,
                "benchmark_version": BENCHMARK_VERSION,
                "development_hypothesis": True,
                "selection": "Fixed fields selected from aggregate same-GT performance; no held-out validation; fusion never reads GT",
                "field_sources": {
                    "discipline_code": "best_clean6",
                    "discipline_name": "baseline",
                    "controls": "onnx_clean",
                },
                "inference_seconds": sum(
                    results[member]["inference_seconds"] for member in members
                ),
                "fusion_seconds": time.perf_counter() - started,
            }
            result["pipeline_seconds"] = (
                result["inference_seconds"]
                + results["baseline"].get("geometry_seconds", 0)
                + result["fusion_seconds"]
            )
            results["hybrid_fields_development"] = result
            _json(args.output / "predictions-hybrid_fields_development.json", result)
    if not args.gt:
        return 0
    # GT is intentionally accessed only here, after independent inference.
    truth = []
    for path in args.gt:
        page = json.loads(path.read_text(encoding="utf-8"))
        if page["source_sha256"] != source_hash:
            raise ValueError(f"GT source hash differs: {path}")
        for row in page["rows"]:
            if row.get("verified") is not True:
                raise ValueError(f"Unverified GT row: {row.get('row_id')}")
            truth.append(dict(row, page=page["page"]))
    metrics, dictionary_metrics = [], []
    for name, result in results.items():
        score, errors = evaluate(truth, result["rows"])
        score.update(
            scenario=name, inference_seconds=result["inference_seconds"], source_sha256=source_hash
        )
        score["development_hypothesis"] = bool(result.get("development_hypothesis"))
        score.update(
            pipeline_seconds=result.get("pipeline_seconds"),
            timing_kind=result.get("timing", {}).get("kind", "constituent_sum"),
            cache_hits=result.get("timing", {}).get("cache_hits"),
            ocr_calls=result.get("timing", {}).get("ocr_calls"),
        )
        metrics.append(score)
        _json(args.output / f"errors-{name}.json", errors)
        dictionary = (
            json.loads(args.dictionary.read_text(encoding="utf-8")) if args.dictionary else None
        )
        if isinstance(dictionary, dict):
            dictionary = dictionary["names"]
        for label, names in [
            ("gt_oracle_upper_bound_DO_NOT_DEPLOY", [row["discipline_name"] for row in truth]),
            ("independent_dictionary", dictionary),
        ]:
            if names is None:
                continue
            suggestions = [
                {
                    "prediction_id": row["prediction_id"],
                    "page": row["page"],
                    **match_name(row["cells"]["discipline_name"].get("text", ""), names),
                }
                for row in result["rows"]
            ]
            _json(
                args.output / f"names-{label}-{name}.json",
                {
                    "label": label,
                    "minimum_similarity": 0.9,
                    "minimum_margin": 0.08,
                    "gt_leakage": label.startswith("gt_oracle"),
                    "suggestions": suggestions,
                },
            )
            for minimum in (0.75, 0.85, 0.90, 0.95):
                for margin in (0.03, 0.08):
                    dictionary_metrics.append(
                        dict(
                            evaluate_dictionary(
                                truth, result["rows"], names, minimum=minimum, margin=margin
                            ),
                            scenario=name,
                            dictionary=label,
                            gt_leakage=label.startswith("gt_oracle"),
                        )
                    )
    _json(
        args.output / "metrics.json",
        {
            "source_sha256": source_hash,
            "gt_rows": len(truth),
            "anls_reference": ANLS_REFERENCE,
            "anls_rule": "lowercase only; preserve whitespace; 1 - NLD when NLD < 0.5; else 0",
            "geometry_match": "greedy one-to-one page/y IoU >= 0.45; no labels",
            "results": metrics,
        },
    )
    _json(args.output / "dictionary-metrics.json", dictionary_metrics)
    production_path = args.output / "production-candidates.json"
    if production_path.exists():
        production = json.loads(production_path.read_text(encoding="utf-8"))
        if production.get("source_sha256") == source_hash:
            geometry_by_page = {}
            for path in args.output.glob("geometry-deskew-page*.json"):
                geometry = json.loads(path.read_text(encoding="utf-8"))
                geometry_by_page[geometry["page"]] = geometry
            _json(
                args.output / "production-candidate-metrics.json",
                evaluate_candidates(truth, production["assessments"], geometry_by_page),
            )
    if metrics:
        with (args.output / "metrics.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=sorted(set().union(*(m.keys() for m in metrics)))
            )
            writer.writeheader()
            writer.writerows(metrics)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

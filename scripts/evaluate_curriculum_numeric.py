"""Separate GT-free numeric inference from independent curriculum evaluation.

The infer command has no GT argument and reads only image cells plus a frozen,
synthetic-only model. The score command does not import the recognizer. Printed
curriculum indices are deliberately excluded from end-to-end identity metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
from collections import Counter
from pathlib import Path

KINDS = ("exam", "pass", "graded_pass", "coursework", "course_project")
FORBIDDEN_LABEL_KEYS = frozenset(
    {
        "gt",
        "ground_truth",
        "expected",
        "expected_text",
        "expected_label",
        "semesters",
        "row_type",
        "is_discipline",
        "controls",
    }
)


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_name(value):
    """Case/Unicode/whitespace normalization without fuzzy or alphabet substitution."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip().casefold()


def normalize_numeric(value):
    """Ignore display wrapping and whitespace, preserving digits and punctuation."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or "")))


def explicit_terms(value):
    """Parse explicitly delimited integer terms; never split a compact `123`."""
    value = normalize_numeric(value)
    if value in ("", "-", "—", "–"):
        return ()
    if not re.fullmatch(r"\d{1,2}(?:,\d{1,2})*", value):
        return None
    values = tuple(sorted(set(map(int, value.split(",")))))
    return values if all(1 <= value <= 12 for value in values) else None


def validate_inference_manifest(manifest):
    """Reject labels and incomplete field exports before any model call."""
    if manifest.get("gt_used") is not False:
        raise ValueError("Inference requires an explicitly GT-free image manifest.")

    def visit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in FORBIDDEN_LABEL_KEYS:
                    raise ValueError(f"Evaluation label is forbidden in inference input: {key}")
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(manifest)
    rows = manifest.get("rows", [])
    if not 0 < len(rows) <= 5000:
        raise ValueError("Expected 1–5000 exported physical rows.")
    seen = set()
    for row in rows:
        key = (row.get("page"), row.get("prediction_id"))
        if key in seen:
            raise ValueError("Duplicate physical row in image manifest.")
        seen.add(key)
        if not set(KINDS).issubset(row.get("cells", {})):
            raise ValueError("Image manifest does not contain all five control columns.")
    if not re.fullmatch(r"[0-9a-f]{64}", manifest.get("source_sha256", "")):
        raise ValueError("Image manifest must identify the source PDF hash.")


def validate_model_provenance(metadata, model_hash, source_hash):
    """Check the declared training boundary; retain the manifest for audit."""
    if metadata.get("synthetic_only") is not True:
        raise ValueError("The numeric evaluation requires declared synthetic-only training.")
    hashes = [metadata[key].lower() for key in ("model_sha256", "sha256") if key in metadata]
    if not hashes or any(value != model_hash.lower() for value in hashes):
        raise ValueError("Model bytes do not match the frozen training metadata hash.")
    sources = metadata.get("training_sources")
    if not sources:
        raise ValueError("Training sources must be explicitly recorded.")
    if source_hash.lower() in json.dumps(sources, ensure_ascii=False).lower():
        raise ValueError("Evaluation PDF appears among training sources.")


def infer_numeric(
    dataset_path, model_path, metadata_path, output_path, *, view="clean", recognizer_factory=None
):
    """Run every numeric cell, including blanks, without opening evaluation labels."""
    import cv2

    from shared_lib.services.curriculum_control_cells import read_control_cell

    dataset_path, model_path, metadata_path, output_path = map(
        Path, (dataset_path, model_path, metadata_path, output_path)
    )
    if output_path.exists():
        raise ValueError(
            "Use a new output path: an older complete result must not mask a failed rerun."
        )
    if view not in ("clean", "raw"):
        raise ValueError("Only raw or clean exported pixels are supported.")
    manifest = json.loads(dataset_path.read_text(encoding="utf-8"))
    validate_inference_manifest(manifest)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    model_hash, metadata_hash, dataset_hash = map(
        _digest, (model_path, metadata_path, dataset_path)
    )
    validate_model_provenance(metadata, model_hash, manifest["source_sha256"])
    if recognizer_factory is None:
        from shared_lib.services.curriculum_numeric import NumericRecognizer

        recognizer_factory = NumericRecognizer
    root = dataset_path.parent.resolve()
    tasks = []
    rows = []
    for source in manifest["rows"]:
        row = {key: source[key] for key in ("page", "prediction_id", "bbox")}
        row["cells"] = {}
        rows.append(row)
        for field in KINDS:
            image_path = (root / source["cells"][field][view + "_path"]).resolve()
            if not image_path.is_relative_to(root) or not image_path.is_file():
                raise ValueError("Missing image or image path outside the frozen dataset.")
            tasks.append((row, field, image_path))
    record = {
        "version": "curriculum-numeric-evaluation-1",
        "complete": False,
        "source_sha256": manifest["source_sha256"],
        "dataset_sha256": dataset_hash,
        "model_sha256": model_hash,
        "model_metadata_sha256": metadata_hash,
        "training_provenance": metadata,
        "ground_truth_loaded": False,
        "printed_indices_recognized": False,
        "headers_recognized": False,
        "external_blank_gate_used": False,
        "pixel_view": view,
        "expected_cells": len(tasks),
        "completed_cells": 0,
        "rows": rows,
    }
    partial_path = output_path.with_suffix(".partial.json")
    _save(partial_path, record)
    started = time.perf_counter()
    recognizer = recognizer_factory(model_path=model_path)
    initialized = time.perf_counter()
    for row, field, image_path in tasks:
        image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError(f"Cannot read numeric cell image {image_path}")
        reading = read_control_cell(image, recognizer)
        if not isinstance(reading, dict) or "text" not in reading:
            raise ValueError("Recognizer returned an invalid cell reading.")
        row["cells"][field] = dict(reading, input_sha256=_digest(image_path))
        record["completed_cells"] += 1
        if record["completed_cells"] % 50 == 0:
            _save(partial_path, record)
            print(f"Numeric inference: {record['completed_cells']}/{len(tasks)} cells", flush=True)
    if [_digest(path) for path in (model_path, metadata_path, dataset_path)] != [
        model_hash,
        metadata_hash,
        dataset_hash,
    ]:
        raise ValueError(
            "Model, metadata or dataset changed during inference; result is not frozen."
        )
    record.update(
        complete=True,
        model_init_seconds=initialized - started,
        inference_seconds=time.perf_counter() - initialized,
    )
    _save(output_path, record)
    _save(
        partial_path,
        {"complete": True, "superseded_by": str(output_path), "model_sha256": model_hash},
    )
    return record


def _y_iou(left, right):
    overlap = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    union = max(left[3], right[3]) - min(left[1], right[1])
    return overlap / union if union > 0 else 0.0


def _x_iou(left, right):
    overlap = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    union = max(left[2], right[2]) - min(left[0], right[0])
    return overlap / union if union > 0 else 0.0


def align_physical_rows(truth_rows, predictions, *, threshold=0.45):
    """One-to-one row alignment uses page and vertical geometry only, never text/code."""
    edges = []
    for i, truth in enumerate(truth_rows):
        for j, pred in enumerate(predictions):
            if (
                truth["page"] == pred.get("page")
                and len(pred.get("bbox", [])) == 4
                and _x_iou(truth["bbox"], pred["bbox"]) >= 0.5
            ):
                score = _y_iou(truth["bbox"], pred["bbox"])
                if score >= threshold:
                    edges.append((score, i, j))
    matched, used = {}, set()
    for score, i, j in sorted(edges, reverse=True):
        if i not in matched and j not in used:
            matched[i] = (j, score)
            used.add(j)
    return matched, set(range(len(predictions))) - used


def score_numeric_cells(truth_rows, predictions):
    """Literal/semantic cell accuracy and abstentions, including missing and extra rows."""
    matches, extras = align_physical_rows(truth_rows, predictions)
    counts = Counter(
        {
            key: 0
            for key in (
                "cells",
                "exact_cells",
                "blank_cells",
                "nonblank_cells",
                "exact_blank_cells",
                "exact_nonblank_cells",
                "raw_blank_false_positive",
                "semantic_blank_false_positive",
                "abstentions",
                "missing_cells",
                "invalid_text_cells",
                "discipline_cells",
                "discipline_literal_exact",
                "discipline_semantic_exact",
                "extra_rows",
                "extra_nonblank_cells",
            )
        }
    )
    details = []
    for index, truth in enumerate(truth_rows):
        matched = matches.get(index)
        pred = predictions[matched[0]] if matched else {}
        for field in KINDS:
            expected = normalize_numeric(truth.get("controls", {}).get(field, ""))
            reading = pred.get("cells", {}).get(field)
            missing = reading is None
            reading = reading or {}
            raw = normalize_numeric(reading.get("text", ""))
            abstained = missing or bool(reading.get("abstained"))
            exact = not abstained and expected == raw
            actual_terms = explicit_terms(raw)
            blank = not expected
            counts["cells"] += 1
            counts["exact_cells"] += exact
            counts["blank_cells" if blank else "nonblank_cells"] += 1
            counts["exact_blank_cells" if blank else "exact_nonblank_cells"] += exact
            counts["raw_blank_false_positive"] += bool(blank and raw and not abstained)
            counts["semantic_blank_false_positive"] += bool(
                blank and actual_terms and not abstained
            )
            counts["abstentions"] += abstained
            counts["missing_cells"] += missing
            counts["invalid_text_cells"] += actual_terms is None and not abstained
            discipline = truth.get("row_type") == "discipline"
            if discipline:
                counts["discipline_cells"] += 1
                counts["discipline_literal_exact"] += exact
                counts["discipline_semantic_exact"] += not abstained and actual_terms == tuple(
                    truth.get("semesters", {}).get(field, [])
                )
            details.append(
                {
                    "row_id": truth["row_id"],
                    "page": truth["page"],
                    "bbox": truth["bbox"],
                    "prediction_id": pred.get("prediction_id", pred.get("source_row")),
                    "discipline_name": truth.get("discipline_name", ""),
                    "row_type": truth.get("row_type"),
                    "field": field,
                    "expected": expected,
                    "predicted": raw,
                    "exact": exact,
                    "abstained": abstained,
                    "missing": missing,
                    "reason": reading.get("reason"),
                    "confidence": reading.get("confidence"),
                    "y_iou": matched[1] if matched else 0,
                }
            )
    counts["extra_rows"] = len(extras)
    for index in extras:
        for field in KINDS:
            reading = predictions[index].get("cells", {}).get(field, {})
            counts["extra_nonblank_cells"] += bool(
                normalize_numeric(reading.get("text")) and not reading.get("abstained")
            )
    result = dict(counts)
    result["literal_accuracy"] = counts["exact_cells"] / counts["cells"] if counts["cells"] else 0
    result["accepted_coverage"] = (
        1 - counts["abstentions"] / counts["cells"] if counts["cells"] else 0
    )
    result["discipline_semantic_accuracy"] = (
        counts["discipline_semantic_exact"] / counts["discipline_cells"]
        if counts["discipline_cells"]
        else 0
    )
    return result, details


def score_assessments(truth_rows, predictions):
    """Strict (physical row, name, kind, semester) facts; printed codes never participate."""
    matches, extras = align_physical_rows(truth_rows, predictions)
    expected_facts, predicted_facts = set(), set()
    counts = Counter(
        {
            key: 0
            for key in (
                "row_classifier_tp",
                "row_classifier_fp",
                "row_classifier_fn",
                "missing_rows",
                "unknown_row_classification",
                "abstained_control_cells",
            )
        }
    )
    for index, truth in enumerate(truth_rows):
        name = normalize_name(truth.get("discipline_name", ""))
        if truth.get("row_type") == "discipline":
            expected_facts.update(
                (truth["page"], truth["row_id"], name, kind, term)
                for kind in KINDS
                for term in truth.get("semesters", {}).get(kind, [])
            )
        matched = matches.get(index)
        if matched is None:
            counts["missing_rows"] += 1
            counts["row_classifier_fn"] += truth.get("row_type") == "discipline"
            continue
        pred = predictions[matched[0]]
        predicted_discipline = pred.get("is_discipline")
        truth_discipline = truth.get("row_type") == "discipline"
        if not isinstance(predicted_discipline, bool):
            counts["unknown_row_classification"] += 1
            predicted_discipline = False
        if predicted_discipline:
            counts["row_classifier_tp" if truth_discipline else "row_classifier_fp"] += 1
        elif truth_discipline:
            counts["row_classifier_fn"] += 1
        predicted_name = normalize_name(
            pred.get("discipline_name")
            or pred.get("cells", {}).get("discipline_name", {}).get("text")
        )
        for kind in KINDS:
            reading = pred.get("cells", {}).get(kind, {})
            if kind not in pred.get("cells", {}) or reading.get("abstained"):
                counts["abstained_control_cells"] += 1
                continue
            if predicted_discipline:
                predicted_facts.update(
                    (truth["page"], truth["row_id"], predicted_name, kind, term)
                    for term in (explicit_terms(reading.get("text", "")) or ())
                )
    for index in extras:
        pred = predictions[index]
        if pred.get("is_discipline"):
            counts["row_classifier_fp"] += 1
            name = normalize_name(
                pred.get("discipline_name")
                or pred.get("cells", {}).get("discipline_name", {}).get("text")
            )
            for kind in KINDS:
                reading = pred.get("cells", {}).get(kind, {})
                if not reading.get("abstained"):
                    predicted_facts.update(
                        (pred.get("page", 0), f"extra_{index}", name, kind, term)
                        for term in (explicit_terms(reading.get("text", "")) or ())
                    )
    true_positives = expected_facts & predicted_facts
    false_positives = predicted_facts - expected_facts
    false_negatives = expected_facts - predicted_facts
    result = dict(
        counts,
        tp=len(true_positives),
        fp=len(false_positives),
        fn=len(false_negatives),
        expected_facts=len(expected_facts),
        predicted_facts=len(predicted_facts),
        printed_code_required=False,
        physical_alignment="one-to-one page+x-IoU >= 0.5+y-IoU >= 0.45",
        name_normalization="NFKC+casefold+whitespace; no fuzzy matching",
    )
    result["precision"] = len(true_positives) / len(predicted_facts) if predicted_facts else None
    result["recall"] = len(true_positives) / len(expected_facts) if expected_facts else None
    return result, {
        "false_positives": sorted(false_positives),
        "false_negatives": sorted(false_negatives),
    }


def load_truth(paths, source_hash):
    rows = []
    for path in paths:
        page = json.loads(Path(path).read_text(encoding="utf-8"))
        if page.get("source_sha256") != source_hash:
            raise ValueError("Evaluation GT belongs to a different source PDF.")
        rows.extend(dict(row, page=page["page"]) for row in page["rows"])
    if not rows or len({(row["page"], row["row_id"]) for row in rows}) != len(rows):
        raise ValueError("GT is empty or contains duplicate physical row identities.")
    return rows


def validate_completed_prediction(result):
    if result.get("complete") is not True or not isinstance(result.get("rows"), list):
        raise ValueError("Partial or unmarked runs cannot receive evaluation scores.")
    if "expected_cells" in result:
        if result.get("completed_cells") != result["expected_cells"]:
            raise ValueError("Partial cell inference cannot receive evaluation scores.")
        actual = sum(
            sum(field in row.get("cells", {}) for field in KINDS) for row in result["rows"]
        )
        if actual != result["expected_cells"]:
            raise ValueError("Recorded cell coverage does not match the completed run.")


def render_contacts(dataset_path, details, output_dir, *, only_errors=False):
    """Create PNG contact sheets of real input cells; only the scoring stage sees labels."""
    from PIL import Image, ImageDraw, ImageFont

    dataset_path, output_dir = Path(dataset_path), Path(output_dir)
    manifest = json.loads(dataset_path.read_text(encoding="utf-8"))
    root = dataset_path.parent.resolve()
    rows = {(row["page"], row["prediction_id"]): row for row in manifest["rows"]}
    selected = [item for item in details if not only_errors or not item["exact"]]
    fonts = [
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    font_path = next((path for path in fonts if path.is_file()), None)
    font = ImageFont.truetype(str(font_path), 13) if font_path else ImageFont.load_default()
    output_dir.mkdir(parents=True, exist_ok=True)
    result = []
    for start in range(0, len(selected), 80):
        chunk = selected[start : start + 80]
        sheet = Image.new("RGB", (8 * 220, ((len(chunk) + 7) // 8) * 136), "#eef2f6")
        draw = ImageDraw.Draw(sheet)
        for index, item in enumerate(chunk):
            x, y = (index % 8) * 220, (index // 8) * 136
            color = "#167345" if item["exact"] else "#a86100" if item["abstained"] else "#b4232c"
            draw.rounded_rectangle(
                (x + 3, y + 3, x + 216, y + 132), radius=6, fill="white", outline=color, width=2
            )
            draw.text(
                (x + 9, y + 8), f"{item['row_id']} · {item['field']}", fill="#253044", font=font
            )
            source = rows.get((item["page"], item.get("prediction_id") or item["row_id"]))
            if source:
                image_path = (root / source["cells"][item["field"]]["clean_path"]).resolve()
                if not image_path.is_relative_to(root):
                    raise ValueError("Contact image path escapes its dataset.")
                with Image.open(image_path) as image:
                    image = image.convert("RGB")
                    image.thumbnail((198, 65))
                    sheet.paste(
                        image,
                        (x + 10 + (198 - image.width) // 2, y + 29 + (65 - image.height) // 2),
                    )
            draw.text(
                (x + 9, y + 98),
                f"GT: {item['expected'] or '∅'}  →  {item['predicted'] or '∅'}",
                fill=color,
                font=font,
            )
            label = (
                "abstained" if item["abstained"] else "correct" if item["exact"] else "incorrect"
            )
            draw.text((x + 9, y + 115), label, fill=color, font=font)
        path = (
            output_dir / f"contacts-{'errors' if only_errors else 'all'}-{start // 80 + 1:03d}.png"
        )
        sheet.save(path)
        result.append(str(path))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    infer = commands.add_parser("infer")
    infer.add_argument("--dataset", type=Path, required=True)
    infer.add_argument("--model", type=Path, required=True)
    infer.add_argument("--metadata", type=Path, required=True)
    infer.add_argument("--output", type=Path, required=True)
    infer.add_argument("--view", choices=("clean", "raw"), default="clean")
    score = commands.add_parser("score")
    score.add_argument("--predictions", type=Path, required=True)
    score.add_argument("--gt", type=Path, nargs="+", required=True)
    score.add_argument("--output", type=Path, required=True)
    score.add_argument("--end-to-end", action="store_true")
    score.add_argument("--contact-dataset", type=Path)
    args = parser.parse_args(argv)
    if args.command == "infer":
        result = infer_numeric(args.dataset, args.model, args.metadata, args.output, view=args.view)
        print(
            json.dumps(
                {
                    key: result[key]
                    for key in ("complete", "completed_cells", "model_sha256", "inference_seconds")
                }
            )
        )
    else:
        result = json.loads(args.predictions.read_text(encoding="utf-8"))
        validate_completed_prediction(result)
        truth = load_truth(args.gt, result.get("source_sha256"))
        metrics, details = score_numeric_cells(truth, result["rows"])
        report = {
            "source_sha256": result.get("source_sha256"),
            "prediction_sha256": _digest(args.predictions),
            "model_sha256": result.get("model_sha256"),
            "numeric_metrics": metrics,
            "cells": details,
        }
        if args.end_to_end:
            report["assessment_metrics"], report["assessment_errors"] = score_assessments(
                truth, result["rows"]
            )
        if args.contact_dataset:
            report["contact_sheets"] = render_contacts(
                args.contact_dataset, details, args.output.parent / "contacts"
            )
            report["error_sheets"] = render_contacts(
                args.contact_dataset, details, args.output.parent / "contacts", only_errors=True
            )
        _save(args.output, report)
        print(
            json.dumps(
                {key: value for key, value in report.items() if key.endswith("metrics")},
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Fixed, auditable field routing for curriculum OCR experiments, without GT."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmark_curriculum_ocr import (  # noqa: E402
    FIELDS,
    KINDS,
    classify_rows,
    control_semesters,
)
from shared_lib.services.curriculum_ocr import _code  # noqa: E402

FUSION_VERSION = "typed-fields-consensus-1"


def _index(result):
    rows = {}
    for row in result["rows"]:
        key = (row["page"], row["prediction_id"])
        if key in rows:
            raise ValueError("Duplicate physical row ID in model predictions")
        rows[key] = row
    return rows


def fuse_predictions(names: dict, codes: dict, numeric_a: dict, numeric_b: dict) -> dict:
    """Route fixed fields; require paired numeric agreement and valid code fallback.

    Model roles were selected on the 2023 development set, not on held-out data.
    No expected values, discipline dictionary, row answer or GT is accepted.
    """
    sources = {"names": names, "codes": codes, "numeric_a": numeric_a, "numeric_b": numeric_b}
    hashes = {source.get("source_sha256") for source in sources.values()}
    if None in hashes or len(hashes) != 1:
        raise ValueError("Predictions must refer to exactly one verified source hash")
    indices = {name: _index(source) for name, source in sources.items()}
    if any(set(index) != set(indices["names"]) for index in indices.values()):
        raise ValueError("All recognizers must retain the same physical rows")
    rows = []
    for key, first in indices["names"].items():
        row = {
            name: copy.deepcopy(value)
            for name, value in first.items()
            if name not in {"cells", "is_discipline"}
        }
        readings = {name: index[key].get("cells", {}) for name, index in indices.items()}
        cells = {}
        for field in FIELDS:
            missing = {"text": "", "abstained": True, "error": "missing_source_field"}
            role = (
                "names"
                if field == "discipline_name"
                else "codes"
                if field == "discipline_code"
                else "numeric_a"
            )
            selected = copy.deepcopy(readings[role].get(field, missing))
            alternatives = [
                copy.deepcopy(readings[r].get(field, missing)) for r in ("numeric_a", "numeric_b")
            ]
            if field == "discipline_code":
                valid = None if selected.get("abstained") else _code(selected.get("text", ""))
                if not valid:
                    normalized = [
                        None if c.get("abstained") else _code(c.get("text", ""))
                        for c in alternatives
                    ]
                    if normalized[0] and normalized[0] == normalized[1]:
                        selected = copy.deepcopy(alternatives[0])
                        selected["fallback_reason"] = (
                            "primary_invalid_and_two_valid_index_readings_agree"
                        )
                        role = "numeric_a+numeric_b_index_agreement"
                    else:
                        selected = dict(
                            selected, abstained=True, error="no_valid_agreed_discipline_index"
                        )
                selected["alternative_readings"] = alternatives
            elif field in KINDS:
                values = [
                    None if c.get("abstained") else control_semesters(c.get("text", ""))
                    for c in alternatives
                ]
                # Preserve section counts literally for audit. Their conversion to
                # course facts is a later, independent row-classification step.
                literal_agreement = (
                    alternatives[0].get("text", "").strip()
                    == alternatives[1].get("text", "").strip()
                )
                agreed = not any(c.get("abstained") for c in alternatives) and (
                    values[0] is not None and values[0] == values[1] or literal_agreement
                )
                if not agreed:
                    selected = dict(
                        selected, text="", abstained=True, error="numeric_model_disagreement"
                    )
                selected["alternative_readings"] = alternatives
                role = "numeric_pair_agreement"
            selected["selected_role"] = role
            cells[field] = selected
        row["cells"] = cells
        rows.append(row)
    return {
        "scenario": "typed_fields_consensus_development",
        "source_sha256": next(iter(hashes)),
        "fusion_version": FUSION_VERSION,
        "development_hypothesis": True,
        "selection_note": "Fixed field roles chosen on 2023 development aggregate scores; no row-specific GT selection.",
        "gt_used_for_inference": False,
        "rows": classify_rows(rows),
        "sources": {
            role: source.get("scenario", source.get("name", role))
            for role, source in sources.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("names", "codes", "numeric-a", "numeric-b", "output"):
        parser.add_argument("--" + field, type=Path, required=True)
    args = parser.parse_args()
    result = fuse_predictions(
        *[
            json.loads(getattr(args, name).read_text(encoding="utf-8"))
            for name in ("names", "codes", "numeric_a", "numeric_b")
        ]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(args.output.resolve()), "rows": len(result["rows"])}))


if __name__ == "__main__":
    main()

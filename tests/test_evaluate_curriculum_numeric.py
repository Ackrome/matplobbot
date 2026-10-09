"""Honest evaluation boundaries for the curriculum numeric recognizer."""

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.evaluate_curriculum_numeric import (
    KINDS,
    align_physical_rows,
    explicit_terms,
    infer_numeric,
    score_assessments,
    score_numeric_cells,
    validate_completed_prediction,
    validate_inference_manifest,
    validate_model_provenance,
)


def truth(row_id="r1", *, page=1, name="Математика", kind="exam", term=3, row_type="discipline"):
    return {
        "row_id": row_id,
        "page": page,
        "bbox": [0.1, 0.2, 0.5, 0.3],
        "row_type": row_type,
        "discipline_code": "Б.1.1",
        "discipline_name": name,
        "controls": {field: str(term) if field == kind and term else "" for field in KINDS},
        "semesters": {
            field: [term] if field == kind and term and row_type == "discipline" else []
            for field in KINDS
        },
    }


def prediction(source, **changes):
    value = {
        "page": source["page"],
        "bbox": source["bbox"],
        "prediction_id": source["row_id"],
        "discipline_name": source["discipline_name"],
        "is_discipline": source["row_type"] == "discipline",
        "cells": {
            field: {"text": source["controls"][field], "abstained": False} for field in KINDS
        },
    }
    return dict(value, **changes)


class NumericMetricTests(unittest.TestCase):
    def test_missing_or_abstained_blanks_are_not_correct(self):
        gt = truth(term=None)
        pred = prediction(gt)
        del pred["cells"]["pass"]
        pred["cells"]["exam"]["abstained"] = True
        result, _ = score_numeric_cells([gt], [pred])
        self.assertEqual(result["exact_cells"], 3)
        self.assertEqual(result["abstentions"], 2)
        self.assertEqual(result["missing_cells"], 1)

    def test_false_additions_to_blank_cells_count(self):
        gt = truth(term=None)
        pred = prediction(gt)
        pred["cells"]["pass"]["text"] = "2"
        result, _ = score_numeric_cells([gt], [pred])
        self.assertEqual(result["raw_blank_false_positive"], 1)
        self.assertEqual(result["semantic_blank_false_positive"], 1)

    def test_sections_score_literal_counts_without_semester_inheritance(self):
        gt = truth(term=30, row_type="section")
        result, _ = score_numeric_cells([gt], [prediction(gt)])
        self.assertEqual(result["exact_cells"], 5)
        self.assertEqual(result["discipline_cells"], 0)
        metrics, _ = score_assessments([gt], [prediction(gt)])
        self.assertEqual(metrics["expected_facts"], 0)

    def test_no_compact_digit_guessing(self):
        self.assertIsNone(explicit_terms("123"))
        self.assertEqual(explicit_terms("1,2, 3"), (1, 2, 3))
        self.assertIsNone(explicit_terms("3-5"))
        self.assertEqual(explicit_terms("-"), ())


class EndToEndMetricTests(unittest.TestCase):
    def test_printed_code_is_not_part_of_identity(self):
        gt = truth()
        pred = prediction(gt, discipline_code="OCR totally wrong")
        metrics, _ = score_assessments([gt], [pred])
        self.assertEqual((metrics["tp"], metrics["fp"], metrics["fn"]), (1, 0, 0))

    def test_wrong_name_is_false_positive_and_false_negative(self):
        gt = truth()
        metrics, _ = score_assessments([gt], [prediction(gt, discipline_name="Физика")])
        self.assertEqual((metrics["tp"], metrics["fp"], metrics["fn"]), (0, 1, 1))

    def test_wrong_kind_is_not_a_match(self):
        gt = truth()
        pred = prediction(gt)
        pred["cells"]["exam"]["text"] = ""
        pred["cells"]["pass"]["text"] = "3"
        metrics, _ = score_assessments([gt], [pred])
        self.assertEqual((metrics["tp"], metrics["fp"], metrics["fn"]), (0, 1, 1))

    def test_wrong_or_missing_geometry_cannot_use_name_to_match(self):
        gt = truth()
        pred = prediction(gt, bbox=[0.7, 0.2, 0.9, 0.3])
        metrics, _ = score_assessments([gt], [pred])
        self.assertEqual((metrics["tp"], metrics["fp"], metrics["fn"]), (0, 1, 1))
        self.assertEqual(align_physical_rows([gt], [pred])[0], {})

    def test_duplicate_predictions_are_not_silently_deduplicated(self):
        gt = truth()
        metrics, _ = score_assessments([gt], [prediction(gt), prediction(gt)])
        self.assertEqual((metrics["tp"], metrics["fp"], metrics["fn"]), (1, 1, 0))

    def test_identical_names_on_different_pages_stay_distinct(self):
        a, b = truth(page=1), truth(page=2)
        metrics, _ = score_assessments([a, b], [prediction(a), prediction(b)])
        self.assertEqual(metrics["tp"], 2)

    def test_section_wrongly_emitted_as_discipline_is_false_positive(self):
        gt = truth(row_type="section")
        metrics, _ = score_assessments([gt], [prediction(gt, is_discipline=True)])
        self.assertEqual((metrics["tp"], metrics["fp"], metrics["fn"]), (0, 1, 0))


class EvaluationBoundaryTests(unittest.TestCase):
    def test_partial_runs_cannot_receive_metrics(self):
        for value in (
            {"complete": False, "rows": []},
            {"rows": []},
            {"complete": True, "rows": [], "expected_cells": 5, "completed_cells": 4},
            {"complete": True, "rows": [], "expected_cells": 5, "completed_cells": 5},
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_completed_prediction(value)

    def test_annotations_are_rejected_inside_nested_input(self):
        base = {
            "gt_used": False,
            "source_sha256": "a" * 64,
            "rows": [
                {
                    "page": 1,
                    "prediction_id": "r1",
                    "cells": {field: {"clean_path": field + ".png"} for field in KINDS},
                }
            ],
        }
        validate_inference_manifest(base)
        contaminated = copy.deepcopy(base)
        contaminated["rows"][0]["cells"]["pass"]["expected_text"] = "3"
        with self.assertRaisesRegex(ValueError, "forbidden"):
            validate_inference_manifest(contaminated)

    def test_training_provenance_rejects_real_data_or_changed_weights(self):
        valid = {
            "synthetic_only": True,
            "sha256": "a" * 64,
            "training_sources": ["synthetic generator", "fonts"],
        }
        validate_model_provenance(valid, "a" * 64, "b" * 64)
        for metadata in (
            dict(valid, synthetic_only=False),
            dict(valid, sha256="c" * 64),
            dict(valid, training_sources=["b" * 64]),
        ):
            with self.assertRaises(ValueError):
                validate_model_provenance(metadata, "a" * 64, "b" * 64)

    def test_inference_reads_every_blank_cell_without_gt(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("optional image dependencies unavailable")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = root / "model.onnx"
            model.write_bytes(b"frozen synthetic model")
            metadata = root / "model.json"
            metadata.write_text(
                json.dumps(
                    {
                        "synthetic_only": True,
                        "sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
                        "training_sources": ["synthetic generator"],
                    }
                ),
                encoding="utf-8",
            )
            cv2.imwrite(str(root / "cell.png"), np.full((20, 20), 255, dtype=np.uint8))
            manifest = {
                "gt_used": False,
                "source_sha256": "a" * 64,
                "rows": [
                    {
                        "page": 1,
                        "prediction_id": "r1",
                        "bbox": [0.1, 0.2, 0.3, 0.4],
                        "cells": {
                            field: {"clean_path": "cell.png", "blank_gate": True} for field in KINDS
                        },
                    }
                ],
            }
            dataset = root / "manifest.json"
            dataset.write_text(json.dumps(manifest), encoding="utf-8")
            calls = []

            class Recognizer:
                def __init__(self, model_path):
                    self.path = model_path

                def read(self, gray):
                    calls.append(gray.shape)
                    return {"text": "", "abstained": False}

            output = root / "predictions.json"
            result = infer_numeric(dataset, model, metadata, output, recognizer_factory=Recognizer)
            self.assertEqual(len(calls), 5)
            self.assertFalse(result["ground_truth_loaded"])
            self.assertFalse(result["external_blank_gate_used"])
            validate_completed_prediction(result)
            with self.assertRaisesRegex(ValueError, "older complete result"):
                infer_numeric(dataset, model, metadata, output, recognizer_factory=Recognizer)


if __name__ == "__main__":
    unittest.main()

"""Field routing invariants without model weights or fixture answers."""

import copy
import json
import unittest

from scripts.benchmark_curriculum_ocr import FIELDS
from scripts.curriculum_ocr_fusion import fuse_predictions


def source(code="Б.1.1", name="Course", exam="3"):
    cells = {field: {"text": ""} for field in FIELDS}
    cells.update(
        discipline_code={"text": code}, discipline_name={"text": name}, exam={"text": exam}
    )
    return {
        "source_sha256": "source",
        "rows": [{"page": 1, "prediction_id": "p1_r001", "bbox": [0, 0, 1, 1], "cells": cells}],
    }


class TestTypedCurriculumFusion(unittest.TestCase):
    def test_fixed_roles_and_two_independent_index_alternatives(self):
        names, codes, a, b = (
            source(name="Correct title"),
            source(code="5.4.1"),
            source(code="6.4.1"),
            source(code="Б.4.1"),
        )
        originals = copy.deepcopy((names, codes, a, b))
        result = fuse_predictions(names, codes, a, b)
        json.dumps(result)
        row = result["rows"][0]
        self.assertTrue(row["is_discipline"])
        self.assertEqual(row["cells"]["discipline_name"]["text"], "Correct title")
        self.assertIn("fallback_reason", row["cells"]["discipline_code"])
        self.assertEqual((names, codes, a, b), originals)

    def test_numeric_disagreement_and_abstention_are_not_empty_values(self):
        a, b = source(exam="3"), source(exam="4")
        result = fuse_predictions(source(), source(), a, b)["rows"][0]["cells"]
        self.assertTrue(result["exam"]["abstained"])
        self.assertEqual(result["exam"]["alternative_readings"][0]["text"], "3")
        a["rows"][0]["cells"]["pass"] = {"text": "", "abstained": True}
        self.assertTrue(
            fuse_predictions(source(), source(), a, b)["rows"][0]["cells"]["pass"]["abstained"]
        )

    def test_missing_or_mismatched_sources_rejected(self):
        bad = source()
        bad["source_sha256"] = "other"
        with self.assertRaises(ValueError):
            fuse_predictions(source(), source(), source(), bad)
        bad = source()
        bad["rows"] = []
        with self.assertRaises(ValueError):
            fuse_predictions(source(), source(), source(), bad)

    def test_valid_primary_index_not_overwritten(self):
        result = fuse_predictions(
            source(), source(code="Б.1.2"), source(code="Б.1.3"), source(code="Б.1.3")
        )
        self.assertEqual(result["rows"][0]["cells"]["discipline_code"]["text"], "Б.1.2")


if __name__ == "__main__":
    unittest.main()

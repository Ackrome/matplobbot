"""Offline contracts for optional CPU recognizers, without downloading weights."""

import json
import tempfile
import unittest
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None

from scripts.curriculum_ocr_models import constrained_ctc, predict_dataset


@unittest.skipIf(np is None, "optional numpy unavailable")
class RestrictedCtcTests(unittest.TestCase):
    def test_native_decoder_keeps_cyrillic_letter(self):
        output = np.array([[[0.1, 0.3, 0.6]]], dtype=np.float32)
        self.assertEqual(constrained_ctc(output, ["", "3", "з"])[0], "з")

    def test_numeric_decoder_uses_original_digit_probability(self):
        output = np.array([[[0.1, 0.3, 0.6]]], dtype=np.float32)
        before = output.copy()
        text, probabilities = constrained_ctc(output, ["", "3", "з"], numeric=True)
        self.assertEqual(text, "3")
        self.assertAlmostEqual(probabilities[0], 0.3)
        np.testing.assert_array_equal(output, before)

    def test_blank_remains_available_and_no_digit_is_forced(self):
        output = np.array([[[0.3, 0.1, 0.6]]], dtype=np.float32)
        self.assertEqual(constrained_ctc(output, ["", "3", "з"], numeric=True), ("", []))

    def test_numeric_decoder_keeps_multi_digit_counts(self):
        alphabet = ["", "1", "2", ",", " "]
        output = np.eye(len(alphabet), dtype=np.float32)[[1, 2, 3, 4, 2]][None]
        self.assertEqual(constrained_ctc(output, alphabet, numeric=True)[0], "12, 2")

    def test_repeated_labels_use_ctc_blank_semantics(self):
        alphabet = ["", "1", "2"]
        output = np.eye(3, dtype=np.float32)[[1, 1, 0, 1, 2, 2]][None]
        self.assertEqual(constrained_ctc(output, alphabet, numeric=True)[0], "112")

    def test_invalid_probability_in_excluded_class_rejected(self):
        output = np.array([[[0.1, 0.3, float("nan")]]], dtype=np.float32)
        with self.assertRaises(ValueError):
            constrained_ctc(output, ["", "3", "з"], numeric=True)

    def test_model_alphabet_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            constrained_ctc(np.zeros((1, 4, 2)), ["", "1", "2"], numeric=True)

    def test_no_allowed_nonblank_is_safe(self):
        output = np.array([[[0.0, 1.0]]], dtype=np.float32)
        self.assertEqual(constrained_ctc(output, ["", "з"], numeric=True), ("", []))


class DatasetBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "manifest.json"

    def write(self, value):
        self.path.write_text(json.dumps(value), encoding="utf-8")

    def test_gt_manifest_rejected_before_engine_call(self):
        self.write({"gt_used": True, "rows": [{}]})
        with self.assertRaisesRegex(ValueError, "GT-free"):
            predict_dataset(self.path, object())

    def test_missing_gt_provenance_rejected(self):
        self.write({"rows": [{}]})
        with self.assertRaisesRegex(ValueError, "GT-free"):
            predict_dataset(self.path, object())

    def test_path_escape_rejected(self):
        self.write(
            {
                "gt_used": False,
                "rows": [
                    {
                        "cells": {
                            "discipline_code": {"blank_gate": False, "clean_path": "../escape.png"}
                        }
                    }
                ],
            }
        )
        with self.assertRaisesRegex(ValueError, "escapes"):
            predict_dataset(self.path, object())


if __name__ == "__main__":
    unittest.main()

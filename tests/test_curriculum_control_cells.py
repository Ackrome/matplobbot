"""Wrapped-cell semantics without expected real document answers."""

import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from shared_lib.services.curriculum_control_cells import numeric_lines, read_control_cell


class ControlWrappingTests(unittest.TestCase):
    def test_geometry_splits_lines_and_preserves_single_line(self):
        image = np.full((90, 120), 255, np.uint8)
        cv2.putText(image, "5,6,", (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 1)
        cv2.putText(image, "7,8", (8, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 1)
        self.assertEqual(len(numeric_lines(image)), 2)
        self.assertEqual(len(numeric_lines(image[:42])), 1)

    def test_explicit_separator_allows_wrapping_without_guessing(self):
        class Recognizer:
            threshold, model_sha256 = 0.9, "test"

            def __init__(self, values):
                self.values = iter(values)

            def read(self, image):
                value = next(self.values)
                trailing = value.endswith(",")
                return {
                    "text": "" if trailing else value,
                    "raw_text": value,
                    "confidence": 99,
                    "abstained": trailing,
                    "reason": "invalid_sequence" if trailing else "ok",
                }

        with patch(
            "shared_lib.services.curriculum_control_cells.numeric_lines", return_value=[None, None]
        ):
            result = read_control_cell(None, Recognizer(["5,6,", "7,8"]))
            self.assertEqual(result["text"], "5,6,7,8")
            self.assertFalse(result["abstained"])
            result = read_control_cell(None, Recognizer(["12", "34"]))
            self.assertTrue(result["abstained"])
            self.assertEqual(result["text"], "")

    def test_wrapping_cannot_rescue_low_confidence_or_runtime_failure(self):
        for failure in (
            {"reason": "low_confidence", "confidence": 70},
            {"reason": "bounds_error", "confidence": 99},
        ):
            recognizer = Mock(threshold=0.9, model_sha256="test")
            recognizer.read.side_effect = [
                {
                    "raw_text": "5,",
                    "text": "",
                    "confidence": 99,
                    "abstained": True,
                    "reason": "invalid_sequence",
                },
                {"raw_text": "6", "text": "", "abstained": True, **failure},
            ]
            with (
                self.subTest(failure=failure),
                patch(
                    "shared_lib.services.curriculum_control_cells.numeric_lines",
                    return_value=[None, None],
                ),
            ):
                result = read_control_cell(None, recognizer)
                self.assertTrue(result["abstained"])
                self.assertEqual(result["text"], "")


if __name__ == "__main__":
    unittest.main()

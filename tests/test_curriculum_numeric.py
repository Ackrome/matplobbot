"""Numeric recognition contracts, independent of real curriculum answer labels."""

import unittest
from importlib.util import find_spec

from shared_lib.services.curriculum_numeric import (
    ALPHABET,
    NumericRecognizer,
    decode_ctc,
    prepare_cell,
)

AVAILABLE = find_spec("numpy") is not None and find_spec("cv2") is not None


@unittest.skipUnless(AVAILABLE, "Optional CPU image dependencies are unavailable.")
class NumericContractTests(unittest.TestCase):
    def test_ctc_repeated_digits_need_a_blank_separator(self):
        import numpy as np

        path = [2, 2, 0, 2, 11, 3, 3, 0]
        values = np.full((len(path), len(ALPHABET) + 1), 0.001)
        for i, label in enumerate(path):
            values[i, label] = 0.99
        self.assertEqual(decode_ctc(values)[0], "11,2")

    def test_blank_and_single_grid_remnant(self):
        import numpy as np

        for shade in (220, 255):
            image = np.full((40, 80), shade, dtype=np.uint8)
            image[0] = 0
            tensor, diagnostics = prepare_cell(image)
            self.assertTrue(diagnostics["blank"])
            self.assertEqual(float(tensor.max()), 0)

    def test_bounds_and_type_are_enforced(self):
        import numpy as np

        with self.assertRaises(ValueError):
            prepare_cell(np.zeros((2, 2, 3), dtype=np.uint8))
        with self.assertRaises(ValueError):
            prepare_cell(np.zeros((1200, 1200), dtype=np.uint8))

    def test_centered_tightly_cropped_one_is_not_a_grid_line(self):
        import numpy as np

        image = np.full((20, 40), 255, dtype=np.uint8)
        image[:, 19:21] = 0
        _, diagnostics = prepare_cell(image)
        self.assertFalse(diagnostics["blank"])
        self.assertGreater(diagnostics["ink_pixels"], 0)

    def test_no_invented_separator_for_compact_digits(self):
        import numpy as np

        recognizer = object.__new__(NumericRecognizer)
        recognizer.model_sha256, recognizer.threshold, recognizer.input_name = "test", 0.9, "image"
        logits = np.full((1, 6, len(ALPHABET) + 1), -10, dtype=np.float32)
        for i, label in enumerate([2, 0, 3, 0, 4, 0]):
            logits[0, i, label] = 10

        class Session:
            def run(self, _, inputs):
                return [logits]

        recognizer.session = Session()
        cell = np.full((40, 80), 255, dtype=np.uint8)
        cell[12:28, 35:41] = 0
        result = recognizer.read(cell)
        self.assertEqual(result["text"], "123")
        self.assertFalse(result["abstained"])
        logits.fill(-10)
        logits[0, :, 0] = 10
        empty_reading = recognizer.read(cell)
        self.assertTrue(empty_reading["abstained"])
        self.assertEqual(empty_reading["reason"], "nonempty_unreadable")


if __name__ == "__main__":
    unittest.main()

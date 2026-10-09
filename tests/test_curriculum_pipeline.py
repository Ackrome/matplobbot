"""No-header/index OCR contracts and physical row evidence."""

import time
import unittest
from unittest.mock import patch

import numpy as np

from shared_lib.services import curriculum_pipeline as pipeline
from shared_lib.services.curriculum_layout import (
    KNOWN_SOURCE_LAYOUTS,
    LAYOUTS,
    resolve_layout,
    validate_grid,
)


class LayoutTests(unittest.TestCase):
    def test_unknown_source_never_guesses_column_meanings(self):
        with self.assertRaisesRegex(ValueError, "scan_layout_required"):
            resolve_layout("unknown")
        self.assertEqual(resolve_layout("unknown", "fa_compact_v1"), LAYOUTS["fa_compact_v1"])
        for digest, name in KNOWN_SOURCE_LAYOUTS.items():
            self.assertEqual(resolve_layout(digest).name, name)
            other = next(key for key in LAYOUTS if key != name)
            with self.assertRaisesRegex(ValueError, "scan_layout_conflict"):
                resolve_layout(digest, other)

    def test_grid_requires_name_column_and_all_declared_boundaries(self):
        xs = [0, 33, 133, 165, 199, 214, 228, 241, 255, 268, 281]
        ys = [0, 20, 130, 170, 210, 250]
        self.assertEqual(validate_grid(xs, ys, (700, 1000), LAYOUTS["fa_legacy_v1"]), 2)
        for broken in (xs[:8], xs[:5] + xs[6:], [0] + xs):
            with self.assertRaises(ValueError):
                validate_grid(broken, ys, (700, 1000), LAYOUTS["fa_legacy_v1"])


class PipelineTests(unittest.TestCase):
    def fixture(self):
        image = np.full((700, 1000), 255, np.uint8)
        image[130:170, :300] = 200  # a shaded section, whose counts are not semesters
        image[180:195, 140:150] = 0
        image[220:235, 140:150] = 0
        xs = [0, 33, 133, 165, 199, 214, 228, 241, 255, 268, 281]
        ys = [0, 20, 130, 170, 210, 250]
        return image, xs, ys

    def test_only_names_reach_ocr_and_multi_term_values_preserve_row_identity(self):
        image, xs, ys = self.fixture()
        values = iter(["7", "1,2,3", "", "", "", "", "", "", "", "5"])

        class Numeric:
            def read(self, crop):
                return {"text": next(values), "confidence": 98, "abstained": False}

        names = [
            {"text": text, "confidence": 90}
            for text in ("Section", "First course", "Second course")
        ]
        with (
            patch.object(pipeline.raster, "_deskew", return_value=(image, 0)),
            patch.object(pipeline.raster, "_grid", return_value=(xs, ys, image)),
            patch.object(pipeline.raster, "_batch_cells", return_value=names) as ocr,
            patch.object(
                pipeline.raster, "_header_mapping", side_effect=AssertionError("No header OCR")
            ),
            patch.object(
                pipeline.raster, "_code", side_effect=AssertionError("No index recognition")
            ),
        ):
            records, rows, warnings = pipeline.parse_page(
                image,
                2,
                LAYOUTS["fa_legacy_v1"],
                Numeric(),
                deadline=time.monotonic() + 20,
            )
        self.assertEqual(ocr.call_count, 1)
        self.assertEqual([crop.shape[1] for crop in ocr.call_args.args[0]], [93, 93, 93])
        self.assertEqual([r["is_discipline"] for r in rows], [False, True, True])
        self.assertFalse(warnings)
        self.assertEqual(
            [(r["discipline_code"], r["kind"], r["semester"]) for r in records],
            [
                ("scan:p2:r002", "exam", 7),
                ("scan:p2:r002", "pass", 1),
                ("scan:p2:r002", "pass", 2),
                ("scan:p2:r002", "pass", 3),
                ("scan:p2:r003", "graded_pass", 5),
            ],
        )
        self.assertTrue(all(r["ocr"]["identity_method"] == "physical_source_row" for r in records))

    def test_unresolved_and_ambiguous_numeric_values_never_become_facts(self):
        image, xs, ys = self.fixture()
        count = 0

        class Numeric:
            def read(self, crop):
                nonlocal count
                count += 1
                return {
                    "text": "7" if count % 2 else "123",
                    "confidence": 30,
                    "abstained": bool(count % 2),
                    "reason": "uncertain",
                }

        names = [{"text": "Course", "confidence": 90} for _ in range(3)]
        with (
            patch.object(pipeline.raster, "_deskew", return_value=(image, 0)),
            patch.object(pipeline.raster, "_grid", return_value=(xs, ys, image)),
            patch.object(pipeline.raster, "_batch_cells", return_value=names),
        ):
            records, rows, warnings = pipeline.parse_page(
                image,
                1,
                LAYOUTS["fa_legacy_v1"],
                Numeric(),
                deadline=time.monotonic() + 20,
            )
        self.assertFalse(records)
        self.assertEqual(len(warnings), 10)
        self.assertTrue(
            all(
                c["abstained"]
                for row in rows
                for k, c in row["cells"].items()
                if k != "discipline_name"
            )
        )

    def test_name_cleanup_does_not_replace_words(self):
        self.assertEqual(
            pipeline.clean_name("Проектно- технологическая практика ="),
            "Проектно- технологическая практика",
        )
        self.assertEqual(pipeline.clean_name("Ошибко в названии"), "Ошибко в названии")

    def test_rotated_evidence_uses_original_page_coordinates(self):
        from scripts.benchmark_curriculum_ocr import deskew_bbox_to_original

        shape = (1000, 2000)
        geometry = {"width": 2000, "height": 1000, "deskew_degrees": 0.8}
        expected = deskew_bbox_to_original([0.1, 0.2, 0.4, 0.3], geometry)
        actual = pipeline._original_bbox((200, 200, 800, 300), shape, 0.8)
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b, places=5)


if __name__ == "__main__":
    unittest.main()

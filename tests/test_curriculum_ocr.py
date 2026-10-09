"""Offline regressions for grid-bound CPU OCR and conservative review states."""

import base64
import io
import os
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image

from shared_lib.services import curriculum_ocr as ocr
from tests.test_curriculum_documents import HEADERS, synthetic_pdf


class CpuCurriculumOcrTests(unittest.TestCase):
    def test_grid_geometry_does_not_depend_on_ocr_word_order(self):
        image = np.full((700, 1100), 255, np.uint8)
        for x in range(20, 1081, 100):
            cv2.line(image, (x, 30), (x, 660), 0, 2)
        for y in (30, 200, 280, 360, 440, 520, 600, 660):
            cv2.line(image, (20, y), (1020, y), 0, 2)
        cv2.putText(image, "TEST", (230, 330), cv2.FONT_HERSHEY_SIMPLEX, 1, 0, 2)
        xs, ys, clean = ocr._grid(image)
        self.assertEqual(xs[:4], [20, 120, 220, 320])
        self.assertEqual(ys, [30, 200, 280, 360, 440, 520, 600, 660])
        self.assertTrue(np.all(clean[30, 30:1000] == 255))
        self.assertTrue(np.any(clean[300:340, 230:320] < 180))

    def test_small_page_skew_is_corrected_without_changing_dimensions(self):
        image = np.full((600, 1200), 255, np.uint8)
        for y in range(100, 550, 70):
            cv2.line(image, (20, y), (1180, y + 12), 0, 2)
        corrected, degrees = ocr._deskew(image)
        self.assertEqual(corrected.shape, image.shape)
        self.assertAlmostEqual(degrees, 0.59, delta=0.2)

    def test_batched_cells_preserve_source_rows_and_wrapped_reading_order(self):
        cells = [np.full((50, 200), 255, np.uint8) for _ in range(2)]
        words = [
            dict(text="First", top=15, left=50, height=15, width=30, confidence=95),
            dict(text="line", top=15, left=100, height=15, width=30, confidence=92),
            dict(text="wrapped", top=37, left=12, height=15, width=30, confidence=90),
            dict(text="Second", top=95, left=12, height=15, width=30, confidence=88),
            dict(text="GAP", top=64, left=12, height=10, width=30, confidence=80),
        ]
        with patch.object(ocr, "_ocr", return_value=words):
            result = ocr._batch_cells(cells)
        self.assertEqual(
            result,
            [dict(text="First line wrapped", confidence=90), dict(text="Second", confidence=88)],
        )

    def test_code_normalization_never_joins_two_discipline_rows(self):
        self.assertEqual(ocr._code("6.1.2.2.3.3"), "Б.1.2.2.3.3")
        self.assertEqual(ocr._code("B1.O.02"), "Б1.O.02")
        for value in ("Б.1.01 Б.1.02", "Total 7", "71", "Б.1.123456"):
            self.assertIsNone(ocr._code(value), value)

    def test_header_semantics_are_recognized_in_any_physical_order(self):
        image = np.full((600, 2000), 255, np.uint8)
        xs = [0, 100, 400, 500, 600, 700, 800]
        with (
            patch.object(ocr, "_ocr", return_value=[dict(text="Наименование дисциплин")]),
            patch.object(
                ocr,
                "_batch_cells",
                return_value=[
                    dict(text="Зачет с оценкой"),
                    dict(text="Курсовая работа"),
                    dict(text="Экзамен"),
                    dict(text="Зачет"),
                ],
            ),
        ):
            mapping, error = ocr._header_mapping(image, xs, 10, 500)
        self.assertIsNone(error)
        self.assertEqual(mapping, {2: "graded_pass", 3: "coursework", 4: "exam", 5: "pass"})

    def test_duplicate_or_missing_headers_never_use_column_position(self):
        image = np.full((600, 2000), 255, np.uint8)
        xs = [0, 100, 400, 500, 600, 700, 800]
        for texts in (["Экзамен", "Экзамен"], ["", ""]):
            with (
                self.subTest(texts=texts),
                patch.object(ocr, "_ocr", return_value=[dict(text="Наименование дисциплин")]),
                patch.object(ocr, "_batch_cells", return_value=[dict(text=t) for t in texts]),
            ):
                mapping, error = ocr._header_mapping(image, xs, 10, 500)
            self.assertEqual(mapping, {})
            self.assertTrue(error)

    def test_blank_cell_hallucination_and_compact_digits_never_become_facts(self):
        image = np.full((700, 1000), 255, np.uint8)
        cv2.putText(image, "7", (460, 337), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 0, 2)
        cv2.putText(image, "78", (403, 387), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 0, 2)
        xs = [0, 100, 300, 350, 400, 450, 500, 550]
        ys = [20, 300, 350, 400]

        def readings(*values):
            return [dict(text=value, confidence=95) for value in values]

        with (
            patch.object(ocr, "_deskew", return_value=(image, 0)),
            patch.object(ocr, "_grid", return_value=(xs, ys, image)),
            patch.object(ocr, "_header_mapping", return_value=({4: "exam", 5: "pass"}, None)),
            patch.object(
                ocr,
                "_batch_cells",
                side_effect=[
                    readings("Б.1.01", "Б.1.02"),
                    readings("Real course", "Another course"),
                    readings("1", "78"),
                    readings("7", ""),
                ],
            ),
        ):
            rows, warnings = ocr._page_records(image, 2)
        self.assertEqual(
            [(r["discipline_name"], r["semester"], r["kind"]) for r in rows],
            [("Real course", 7, "pass")],
        )
        self.assertTrue(any("ambiguous semester" in warning for warning in warnings))
        self.assertEqual(rows[0]["page"], 2)
        self.assertTrue(rows[0]["ocr"]["review_required"])

    def test_cell_preview_is_a_bounded_real_png(self):
        random = np.random.default_rng(7).integers(0, 255, (300, 2500), dtype=np.uint8)
        value = ocr._preview(random, (0, 20, 2500, 250))
        raw = base64.b64decode(value)
        self.assertLessEqual(len(raw), ocr.MAX_CROP_BYTES)
        with Image.open(io.BytesIO(raw)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertLessEqual(image.width, 1200)

    def test_ocr_cli_is_bounded_no_shell_and_uses_russian_data(self):
        response = SimpleNamespace(
            stdout=(b"level\tleft\ttop\twidth\theight\tconf\ttext\n5\t2\t3\t10\t12\t93.5\t7\n")
        )
        with patch.object(ocr.subprocess, "run", return_value=response) as run:
            result = ocr._ocr(np.full((30, 70), 255, np.uint8), digits=True)
        command = run.call_args.args[0]
        self.assertIn("rus+eng", command)
        self.assertIn("tessedit_char_whitelist=0123456789,;-", command)
        self.assertFalse(run.call_args.kwargs.get("shell", False))
        self.assertLessEqual(run.call_args.kwargs["timeout"], 20)
        self.assertEqual(run.call_args.kwargs["env"]["OMP_THREAD_LIMIT"], "1")
        self.assertEqual(result[0]["confidence"], 93.5)

    def test_tesseract_timeout_and_missing_engine_are_explicit(self):
        image = np.full((30, 70), 255, np.uint8)
        for error, prefix in (
            (FileNotFoundError(), "ocr_unavailable"),
            (subprocess.TimeoutExpired("tesseract", 20), "ocr_timeout"),
        ):
            with self.subTest(error=error), patch.object(ocr.subprocess, "run", side_effect=error):
                with self.assertRaisesRegex(ocr.OcrUnavailable, prefix):
                    ocr._ocr(image)

    def test_tesseract_tsv_literal_quotes_cannot_consume_later_word_rows(self):
        # Observed on the real plan's quoted module titles: Tesseract emits
        # unescaped quotes, so ordinary CSV quoting would turn subsequent TSV
        # records into part of one OCR word and corrupt its row assignment.
        tsv = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\r\n"
            "5\t1\t1\t1\t1\t1\t10\t12\t70\t20\t96\tМодуль\r\n"
            '5\t1\t1\t1\t1\t2\t90\t12\t75\t20\t94\t"Анализ\r\n'
            '5\t1\t1\t1\t1\t3\t180\t12\t80\t20\t90\tданных"\r\n'
            '5\t1\t1\t1\t1\t4\t270\t12\t8\t20\t80\t"\r\n'
            '5\t1\t1\t1\t2\t1\t10\t50\t130\t20\t85\t"Незакрытая\r\n'
            "5\t1\t1\t1\t3\t1\t10\t90\t110\t20\t97\tСледующая\r\n"
            "5\t1\t1\t1\t3\t2\t130\t90\t130\t20\t98\tдисциплина\r\n"
        )
        with patch.object(
            ocr.subprocess, "run", return_value=SimpleNamespace(stdout=tsv.encode("utf-8"))
        ):
            result = ocr._ocr(np.full((130, 320), 255, np.uint8))
        self.assertEqual(
            [word["text"] for word in result],
            ["Модуль", '"Анализ', 'данных"', '"', '"Незакрытая', "Следующая", "дисциплина"],
        )
        self.assertEqual([word["top"] for word in result], [12, 12, 12, 12, 50, 90, 90])
        self.assertEqual(result[-1]["left"], 130)
        self.assertEqual(result[-1]["confidence"], 98)
        self.assertTrue(
            all("\t" not in word["text"] and "\n" not in word["text"] for word in result)
        )

    def test_version_check_and_document_budget_timeout_have_stable_codes(self):
        document = synthetic_pdf([HEADERS])
        with patch.object(
            ocr.subprocess, "run", side_effect=subprocess.TimeoutExpired("tesseract", 5)
        ):
            result = ocr.parse_scanned_curriculum_legacy(document)
        self.assertTrue(result["warnings"][0].startswith("ocr_timeout:"))
        with (
            patch.object(
                ocr.subprocess, "run", return_value=SimpleNamespace(stdout=b"tesseract 5\n")
            ),
            patch.object(ocr.time, "monotonic", side_effect=[0, ocr.MAX_OCR_SECONDS + 1]),
        ):
            result = ocr.parse_scanned_curriculum_legacy(document)
        self.assertTrue(result["warnings"][0].startswith("ocr_timeout:"))
        self.assertEqual(result["assessments"], [])

    def test_mixed_page_selection_and_review_state_with_real_pdf_raster(self):
        document = synthetic_pdf([HEADERS, ["B1.01", "Course", "7", "", "", "", ""]])
        candidate = dict(
            discipline_code="Б1.01",
            discipline_name="Course",
            semester=7,
            kind="exam",
            page=1,
            evidence="source",
            ocr=dict(crop_png_base64="", review_required=True),
        )
        with (
            patch.object(
                ocr.subprocess, "run", return_value=SimpleNamespace(stdout=b"tesseract 5.5.0\n")
            ),
            patch.object(ocr, "_page_records", return_value=([candidate], [])) as page_parser,
        ):
            result = ocr.parse_scanned_curriculum_legacy(document, page_numbers=[1])
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["page_count"], 1)
        self.assertEqual(result["method"], "ocr")
        self.assertIn("5.5.0", result["engine_version"])
        self.assertEqual(result["assessments"], [candidate])
        self.assertEqual(page_parser.call_args.args[1], 1)

    def test_bad_page_selection_and_missing_binary_are_never_empty_success(self):
        document = synthetic_pdf([HEADERS])
        with patch.object(
            ocr.subprocess, "run", return_value=SimpleNamespace(stdout=b"tesseract 5\n")
        ):
            for selection in ([], [0], [2], list(range(1, 10))):
                result = ocr.parse_scanned_curriculum_legacy(document, page_numbers=selection)
                self.assertEqual(result["status"], "needs_review")
                self.assertEqual(result["assessments"], [])
                self.assertIn("page selection", result["warnings"][0])
        with patch.object(ocr.subprocess, "run", side_effect=FileNotFoundError()):
            result = ocr.parse_scanned_curriculum_legacy(document)
        self.assertTrue(result["warnings"][0].startswith("ocr_unavailable"))

    def test_record_limit_discards_partial_results(self):
        document = synthetic_pdf([HEADERS])
        with (
            patch.object(
                ocr.subprocess, "run", return_value=SimpleNamespace(stdout=b"tesseract 5\n")
            ),
            patch.object(ocr, "MAX_OCR_RECORDS", 0),
            patch.object(ocr, "_page_records", return_value=([dict(page=1)], [])),
        ):
            result = ocr.parse_scanned_curriculum_legacy(document)
        self.assertEqual(result["assessments"], [])
        self.assertIn("assessment limit", result["warnings"][0])

    @unittest.skipUnless(
        os.environ.get("CURRICULUM_OCR_TEST_PDF"), "optional local real-scan check"
    )
    def test_local_real_scan_has_reviewable_source_crops(self):
        from pathlib import Path

        result = ocr.parse_scanned_curriculum_legacy(
            Path(os.environ["CURRICULUM_OCR_TEST_PDF"]).read_bytes()
        )
        self.assertEqual(result["status"], "needs_review")
        self.assertTrue(result["assessments"], result["warnings"])
        self.assertTrue(all(row["ocr"]["review_required"] for row in result["assessments"]))
        self.assertTrue(any(row["ocr"]["crop_png_base64"] for row in result["assessments"]))


if __name__ == "__main__":
    unittest.main()

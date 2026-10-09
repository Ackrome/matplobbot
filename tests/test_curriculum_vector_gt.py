"""Independent vector-GT extraction contracts; no OCR or model downloads."""

import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.curriculum_vector_gt import extract_native_gt, native_header_mapping, semester_list


class NativeHeaderTests(unittest.TestCase):
    def test_rotated_headers_and_credit_column_are_distinct(self):
        headers = [
            [
                "",
                "",
                "",
                "",
                "мен\nЭкза",
                "Зачет",
                "оценкой\nс\nЗачет",
                "работа\nКурсовая",
                "проект\nКурсовой",
                "Зачетные\nединицы\n(ECTS)",
            ]
        ]
        self.assertEqual(
            native_header_mapping(headers),
            {"exam": 4, "pass": 5, "graded_pass": 6, "coursework": 7, "course_project": 8},
        )

    def test_columns_may_have_another_order(self):
        self.assertEqual(
            native_header_mapping(
                [["Зачёт с оценкой", "Курсовой проект", "Экзамен", "Курсовая работа", "Зачет"]]
            ),
            {"graded_pass": 0, "course_project": 1, "exam": 2, "coursework": 3, "pass": 4},
        )

    def test_missing_or_duplicate_forms_require_review(self):
        with self.assertRaises(ValueError):
            native_header_mapping([["Зачет", "Экзамен"]])
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            native_header_mapping([["Зачет", "Зачет"]])

    def test_semester_lists_preserve_integer_identity(self):
        self.assertEqual(semester_list("1,2, 3,4"), [1, 2, 3, 4])
        self.assertEqual(semester_list("8,8"), [8])
        self.assertEqual(semester_list(""), [])
        for raw in ("123", "2-4", "8.8", "0", "13", "з"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                semester_list(raw)


class NativeExtractionTests(unittest.TestCase):
    def test_vector_rows_are_independent_of_ocr_and_include_sections(self):
        header = [
            "",
            "",
            "Экзамен",
            "Зачет",
            "Зачет с оценкой",
            "Курсовая работа",
            "Курсовой проект",
        ]
        body = [
            ["Б.1", "Раздел", "10", "", "", "", ""],
            ["Б.1.1", "Гибритный\nискусственный интеллект", "3", "1,2", "", "", ""],
            ["", "ИТОГО", "10", "", "", "", ""],
        ]
        data = [header, *body]
        geometry = [
            SimpleNamespace(cells=[(j * 10, i * 10, j * 10 + 10, i * 10 + 10) for j in range(7)])
            for i in range(4)
        ]
        table = SimpleNamespace(cells=[None] * 28, rows=geometry, extract=lambda: data)
        page = SimpleNamespace(chars=[{}], width=100, height=100, find_tables=lambda: [table])

        class Document:
            pages = [page]

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "native.pdf"
            path.write_bytes(b"native-vector-fixture")
            module = SimpleNamespace(open=lambda _: Document())
            with patch.dict("sys.modules", {"pdfplumber": module}):
                result = extract_native_gt(path)
        self.assertEqual(
            result[0]["source_sha256"], hashlib.sha256(b"native-vector-fixture").hexdigest()
        )
        rows = result[0]["rows"]
        self.assertEqual([row["row_type"] for row in rows], ["section", "discipline", "summary"])
        self.assertEqual(rows[0]["controls"]["exam"], "10")
        self.assertEqual(rows[0]["semesters"]["exam"], [])
        self.assertEqual(rows[1]["discipline_name"], "Гибритный искусственный интеллект")
        self.assertEqual(rows[1]["semesters"]["pass"], [1, 2])
        self.assertEqual(rows[1]["bbox"], [0.0, 0.2, 0.7, 0.3])


if __name__ == "__main__":
    unittest.main()

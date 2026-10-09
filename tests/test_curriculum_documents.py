"""Synthetic PDF and HTTP regressions; fixtures contain no real student data."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import aiohttp

from shared_lib.services.curriculum_documents import (
    CurriculumDocumentError,
    _table_records,
    fetch_official_document,
    parse_curriculum_pdf,
    validate_official_document_url,
)


def synthetic_pdf(rows, *, draw_grid=True, caption=""):
    """Minimal ASCII PDF, generated in memory to test actual cell extraction."""
    widths = [65, 170, 55, 55, 80, 75, 85]
    xs = [20]
    for width in widths:
        xs.append(xs[-1] + width)
    height = 500
    commands = []
    if caption:
        commands.append(f"BT /F1 9 Tf 20 530 Td ({caption}) Tj ET")
    if draw_grid:
        for x in xs:
            commands.append(f"{x} {height} m {x} {height - 28 * len(rows)} l S")
        for index in range(len(rows) + 1):
            y = height - 28 * index
            commands.append(f"20 {y} m {xs[-1]} {y} l S")
    for index, row in enumerate(rows):
        for column, value in enumerate(row):
            escaped = value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.append(
                f"BT /F1 9 Tf {xs[column] + 3} {height - index * 28 - 17} Td ({escaped}) Tj ET"
            )
    stream = "\n".join(commands).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 650 550] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    )
    return bytes(data)


HEADERS = ["Code", "Discipline", "Exam", "Pass", "Graded pass", "Coursework", "Course project"]


class CurriculumPdfTests(unittest.TestCase):
    def test_real_grid_extraction_preserves_forms_semesters_and_provenance(self):
        result = parse_curriculum_pdf(
            synthetic_pdf(
                [
                    HEADERS,
                    ["B1.01", "Machine learning", "7", "5,6", "", "7", ""],
                    ["B1.02", "Data analysis", "", "", "8", "", "8"],
                ]
            )
        )
        self.assertEqual(result["status"], "parsed", result["warnings"])
        self.assertEqual(result["page_count"], 1)
        records = result["assessments"]
        self.assertEqual(
            {(r["discipline_code"], r["semester"], r["kind"]) for r in records},
            {
                ("B1.01", 7, "exam"),
                ("B1.01", 5, "pass"),
                ("B1.01", 6, "pass"),
                ("B1.01", 7, "coursework"),
                ("B1.02", 8, "graded_pass"),
                ("B1.02", 8, "course_project"),
            },
        )
        self.assertTrue(
            all(r["page"] == 1 and r["discipline_name"] in r["evidence"] for r in records)
        )

    def test_compact_digits_and_markers_are_never_guessed(self):
        for value in ("78", "+", "7?", "7/8", "0", "12", "13"):
            with self.subTest(value=value):
                result = parse_curriculum_pdf(
                    synthetic_pdf(
                        [
                            HEADERS,
                            ["B1.01", "Machine learning", value, "", "", "", ""],
                        ]
                    )
                )
                self.assertEqual(result["status"], "needs_review")
                self.assertEqual(result["assessments"], [])

    def test_two_digit_semester_requires_explicit_document_header(self):
        result = parse_curriculum_pdf(
            synthetic_pdf(
                [HEADERS, ["B1.01", "Machine learning", "12", "", "", "", ""]],
                caption="Semester 12",
            )
        )
        self.assertEqual(result["status"], "parsed", result["warnings"])
        self.assertEqual(result["assessments"][0]["semester"], 12)

    def test_record_budget_does_not_import_a_truncated_curriculum(self):
        document = synthetic_pdf([HEADERS, ["B1.01", "Machine learning", "7", "5,6", "", "7", ""]])
        with patch("shared_lib.services.curriculum_documents.MAX_ASSESSMENTS", 3):
            result = parse_curriculum_pdf(document)
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["page_count"], 1)
        self.assertEqual(result["assessments"], [])
        self.assertIn("assessment record limit", result["warnings"][0])

    def test_cumulative_character_and_table_budgets_stop_parsing(self):
        document = synthetic_pdf([HEADERS, ["B1.01", "Machine learning", "7", "", "", "", ""]])
        with patch("shared_lib.services.curriculum_documents.MAX_TOTAL_CHARACTERS", 10):
            result = parse_curriculum_pdf(document)
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["assessments"], [])
        self.assertIn("total character limit", result["warnings"][0])
        with patch("shared_lib.services.curriculum_documents.MAX_TABLES_PER_PAGE", 0):
            result = parse_curriculum_pdf(document)
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["assessments"], [])
        self.assertIn("table limit", result["warnings"][0])

    def test_missing_headers_and_unruled_text_need_review(self):
        for rows, grid in (
            (
                [
                    ["", "Discipline", "", "", "", "", ""],
                    ["B1.01", "Machine learning", "7", "", "", "", ""],
                ],
                True,
            ),
            ([HEADERS, ["B1.01", "Machine learning", "7", "", "", "", ""]], False),
        ):
            with self.subTest(grid=grid):
                result = parse_curriculum_pdf(synthetic_pdf(rows, draw_grid=grid))
                self.assertEqual(result["status"], "needs_review")
                self.assertEqual(result["assessments"], [])

    def test_parent_totals_are_not_semesters(self):
        result = parse_curriculum_pdf(
            synthetic_pdf(
                [
                    HEADERS,
                    ["B1.01", "Specialized subjects", "3", "", "", "", ""],
                    ["B1.01.01", "Machine learning", "7", "", "", "", ""],
                    ["", "Total", "3", "", "", "", ""],
                ]
            )
        )
        self.assertEqual([r["discipline_code"] for r in result["assessments"]], ["B1.01.01"])
        self.assertEqual(result["status"], "parsed", result["warnings"])

    def test_conflicting_names_and_partial_cells_need_review(self):
        result = parse_curriculum_pdf(
            synthetic_pdf(
                [
                    HEADERS,
                    ["B1.01", "Machine learning", "7", "", "", "", ""],
                    ["B1.01", "Other elective", "8", "?", "", "", ""],
                ]
            )
        )
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(len(result["assessments"]), 2)
        self.assertTrue(any("different names" in w for w in result["warnings"]))

    def test_parent_with_only_blank_children_is_not_a_discipline(self):
        result = parse_curriculum_pdf(
            synthetic_pdf(
                [
                    HEADERS,
                    ["B2.1", "Study practice", "", "", "8", "", ""],
                    ["B2.1.1", "Project practice", "", "", "", "", ""],
                    ["B2.2", "Industrial practice", "", "", "8", "", ""],
                    ["B2.2.1", "Production practice", "", "", "", "", ""],
                    ["B2.2.2", "Diploma practice", "", "", "", "", ""],
                    ["B2.10", "Unrelated course", "7", "", "", "", ""],
                ]
            )
        )
        self.assertEqual(result["status"], "parsed", result["warnings"])
        self.assertEqual(
            [(r["discipline_code"], r["kind"], r["semester"]) for r in result["assessments"]],
            [("B2.10", "exam", 7)],
        )

    def test_all_blank_children_do_not_inherit_parent_assessments(self):
        result = parse_curriculum_pdf(
            synthetic_pdf(
                [
                    HEADERS,
                    ["B2.1", "Study practice", "", "", "8", "", ""],
                    ["B2.1.1", "Project practice", "", "", "", "", ""],
                ]
            )
        )
        self.assertEqual(result["assessments"], [])
        self.assertEqual(result["status"], "needs_review")
        self.assertIn("No unambiguous", result["warnings"][-1])

    def test_repeated_rows_deduplicate_and_ranges_are_explicit(self):
        row = ["B1.01", "Machine learning", "", "5-7", "", "", ""]
        result = parse_curriculum_pdf(synthetic_pdf([HEADERS, row, row]))
        self.assertEqual(result["status"], "parsed", result["warnings"])
        self.assertEqual([r["semester"] for r in result["assessments"]], [5, 6, 7])

    def test_russian_rotated_headers_and_merged_name_geometry(self):
        rows = [
            [
                "Наименование блоков, содержательных модулей, дисциплин",
                None,
                "По семестрам",
                None,
                None,
                None,
                None,
            ],
            [
                None,
                None,
                "мен\nЭкза",
                "Зачет",
                "оценкой\nс\nЗачет",
                "работа\nКурсовая",
                "проект\nКурсовой",
            ],
            ["Б.1.1.1", "Теория вероятностей", "3", "2", "", "", ""],
        ]
        table = SimpleNamespace(
            extract=lambda: rows,
            rows=[
                SimpleNamespace(cells=[(0, 0, 200, 20), None] + [None] * 5),
                SimpleNamespace(
                    cells=[None, None] + [(200 + i * 20, 20, 220 + i * 20, 40) for i in range(5)]
                ),
                SimpleNamespace(
                    cells=[(0, 40, 50, 60), (50, 40, 200, 60)]
                    + [(200 + i * 20, 40, 220 + i * 20, 60) for i in range(5)]
                ),
            ],
        )
        records, warnings = _table_records(table, 2, 8)
        self.assertEqual(warnings, [])
        self.assertEqual({(r["semester"], r["kind"]) for r in records}, {(3, "exam"), (2, "pass")})
        table.rows[0].cells[0] = (0, 0, 50, 20)
        records, warnings = _table_records(table, 2, 8)
        self.assertEqual(records, [])
        self.assertTrue(warnings)

    def test_invalid_blank_and_oversized_documents(self):
        for content in (b"html", b"%PDF-malformed", synthetic_pdf([])):
            with self.subTest(prefix=content[:20]):
                result = parse_curriculum_pdf(content)
                self.assertEqual(result["status"], "needs_review")
                self.assertEqual(result["assessments"], [])
        with patch("shared_lib.services.curriculum_documents.MAX_DOCUMENT_BYTES", 10):
            result = parse_curriculum_pdf(synthetic_pdf([HEADERS]))
        self.assertIn("size limit", result["warnings"][0])


class FakeResponse:
    def __init__(self, body=b"%PDF-1.4", status=200, headers=None, content_length=None):
        self.status, self.headers, self.content_length = status, headers or {}, content_length
        self.body = body
        self.content = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def iter_chunked(self, size):
        for start in range(0, len(self.body), 5):
            yield self.body[start : start + 5]


class FakeSession:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


class CurriculumDownloadTests(unittest.IsolatedAsyncioTestCase):
    def test_url_allowlist_rejects_credentials_ports_encoded_traversal_and_other_hosts(self):
        for url in (
            "http://fa.ru/upload/a.pdf",
            "https://evil.test/upload/a.pdf",
            "https://fa.ru.evil.test/upload/a.pdf",
            "https://user:pass@fa.ru/upload/a.pdf",
            "https://fa.ru:8080/upload/a.pdf",
            "https://fa.ru/admin/a.pdf",
            "https://fa.ru/upload/%252e%252e/private.pdf",
            "https://fa.ru/upload/a\\b.pdf",
            "https://fa.ru/upload/a\n.pdf",
            "https://fa.ru/upload/%00a.pdf",
        ):
            with self.subTest(url=url), self.assertRaises(CurriculumDocumentError):
                validate_official_document_url(url)
        self.assertEqual(
            validate_official_document_url("https://www.fa.ru:443/upload/a.pdf#page=2"),
            "https://www.fa.ru/upload/a.pdf",
        )

    async def test_download_and_official_redirect(self):
        session = FakeSession(
            FakeResponse(status=302, headers={"Location": "https://www.fa.ru/upload/new.pdf"}),
            FakeResponse(),
        )
        self.assertEqual(
            await fetch_official_document(session, "https://fa.ru/upload/a.pdf"), b"%PDF-1.4"
        )
        self.assertEqual(len(session.calls), 2)
        self.assertFalse(session.calls[0][1]["allow_redirects"])

    async def test_external_redirect_is_never_requested(self):
        session = FakeSession(
            FakeResponse(status=302, headers={"Location": "https://127.0.0.1/private"})
        )
        with self.assertRaises(CurriculumDocumentError):
            await fetch_official_document(session, "https://fa.ru/upload/a.pdf")
        self.assertEqual(len(session.calls), 1)

    async def test_http_non_pdf_timeout_and_stream_size_fail(self):
        for response in (
            FakeResponse(status=403),
            FakeResponse(body=b"<html>"),
            TimeoutError(),
            aiohttp.ClientError(),
        ):
            with self.subTest(response=response), self.assertRaises(CurriculumDocumentError):
                await fetch_official_document(FakeSession(response), "https://fa.ru/upload/a.pdf")
        for response in (
            FakeResponse(body=b"%PDF-123456789012345"),
            FakeResponse(content_length=50),
        ):
            with (
                patch("shared_lib.services.curriculum_documents.MAX_DOCUMENT_BYTES", 10),
                self.assertRaises(CurriculumDocumentError),
            ):
                await fetch_official_document(FakeSession(response), "https://fa.ru/upload/a.pdf")


if __name__ == "__main__":
    unittest.main()

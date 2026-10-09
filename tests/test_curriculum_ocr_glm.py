"""Offline contracts for positional GLM table mapping, with no model downloads."""

import unittest

from scripts.curriculum_ocr_glm import map_chunk, parse_table


class GlmTableMappingTests(unittest.TestCase):
    def test_preserves_blank_columns_and_wrapped_text(self):
        self.assertEqual(
            parse_table("<table><tr><td>A<br>B</td><td></td><td>3</td></tr></table>"),
            [["A B", "", "3"]],
        )

    def test_spans_do_not_copy_label_into_empty_assessment(self):
        html = '<table><tr><td colspan="2">Section</td><td rowspan="2">3</td></tr><tr><td>A</td><td>B</td></tr></table>'
        self.assertEqual(parse_table(html), [["Section", "", "3"], ["A", "B", ""]])

    def test_rejects_truncated_and_multiple_tables(self):
        for html in (
            "<table><tr><td>3",
            "<table></table><table></table>",
            '<table><tr><td rowspan="2">3</td></tr></table>',
        ):
            with self.subTest(html=html), self.assertRaises(ValueError):
                parse_table(html)

    def test_mapping_requires_exact_row_and_column_count(self):
        page = {"header_mapping": {"2": "exam"}}
        chunk = {"row_ids": ["p1_r1"]}
        rows = {"p1_r1": {"page": 1, "bbox": [0, 0, 1, 1]}}
        self.assertEqual(
            map_chunk([["X", "Y", "3"]], chunk, page, rows)[0]["cells"]["exam"]["text"], "3"
        )
        for table in ([], [["X", "Y"]], [["X", "Y", "3", ""]]):
            with self.subTest(table=table), self.assertRaises(ValueError):
                map_chunk(table, chunk, page, rows)


if __name__ == "__main__":
    unittest.main()

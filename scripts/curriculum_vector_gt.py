"""Extract independent evaluation labels from a native FA curriculum PDF.

This helper reads PDF vectors/text only. It never imports OCR, its predictions,
the 2023 GT, fuzzy course names or semester lookup rules. Its output is a clean
layout regression reference, not a substitute for manually checked scan GT.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

KINDS = ("exam", "pass", "graded_pass", "coursework", "course_project")
CODE = re.compile(r"^Б\.(?:\d+\.)*\d+$")


def join_text(value):
    """Join PDF display wraps without correcting spelling or lexical content."""
    return re.sub(r"\s+", " ", value or "").strip()


def native_header_mapping(header_rows):
    """Match the five forms by native (including rotated) PDF header text."""
    width = max(map(len, header_rows), default=0)
    result = {}
    for column in range(width):
        words = "".join((row[column] or "") for row in header_rows if column < len(row))
        text = re.sub(r"\s+", "", words).lower().replace("ё", "е")
        field = None
        if "экза" in text:
            field = "exam"
        elif "зачет" in text and "оценк" in text:
            field = "graded_pass"
        elif re.fullmatch(r"зачет(?:ы)?", text):
            field = "pass"
        elif "курсов" in text and "работ" in text:
            field = "coursework"
        elif "курсов" in text and "проект" in text:
            field = "course_project"
        if field:
            if field in result:
                raise ValueError(f"Ambiguous native header: {field}")
            result[field] = column
    if set(result) != set(KINDS):
        raise ValueError("Could not identify every native assessment header.")
    return result


def semester_list(value):
    """Parse explicit integer lists; reject ambiguous digits or ranges in GT."""
    if not value:
        return []
    if not re.fullmatch(r"\d{1,2}(?:\s*,\s*\d{1,2})*", value):
        raise ValueError(f"Review non-list native assessment value: {value!r}")
    result = sorted({int(term.strip()) for term in value.split(",")})
    if any(term < 1 or term > 12 for term in result):
        raise ValueError(f"Review out-of-range native semester value: {value!r}")
    return result


def extract_native_gt(pdf_path):
    """Return page GT objects with vector-cell boxes and source text provenance."""
    import pdfplumber

    path = Path(pdf_path)
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    pages = []
    all_rows = []
    with pdfplumber.open(path) as document:
        for number, page in enumerate(document.pages, 1):
            if not page.chars:
                raise ValueError(
                    "Scanned page has no native text; this is not an OCR GT generator."
                )
            tables = page.find_tables()
            if not tables:
                continue
            table = max(tables, key=lambda candidate: len(candidate.cells))
            data = table.extract()
            first = next(
                (i for i, row in enumerate(data) if CODE.fullmatch(join_text(row[0]))), None
            )
            if first is None:
                # Header-only continuation page: no physical curriculum rows.
                continue
            mapping = native_header_mapping(data[:first])
            rows = []
            for physical_index, (row, geometry) in enumerate(
                zip(data[first:], table.rows[first:]), 1
            ):
                code, name = join_text(row[0]), join_text(row[1])
                if not code and not name:
                    raise ValueError("Blank native physical row requires explicit review.")
                if code and not CODE.fullmatch(code):
                    raise ValueError(f"Unexpected native discipline code: {code!r}")
                selected = [
                    geometry.cells[column]
                    for column in (0, 1, *mapping.values())
                    if geometry.cells[column] is not None
                ]
                bbox = [
                    min(cell[0] for cell in selected) / page.width,
                    min(cell[1] for cell in selected) / page.height,
                    max(cell[2] for cell in selected) / page.width,
                    max(cell[3] for cell in selected) / page.height,
                ]
                record = {
                    "row_id": f"p{number}_r{physical_index:03d}",
                    "page": number,
                    "discipline_code": code,
                    "discipline_name": name,
                    "controls": {kind: join_text(row[column]) for kind, column in mapping.items()},
                    "bbox": bbox,
                    "native_table_row": first + physical_index - 1,
                    "verification_method": "native_pdf_vector_cells_not_ocr",
                }
                rows.append(record)
                all_rows.append(record)
            pages.append(
                {
                    "page": number,
                    "source_sha256": sha256,
                    "source_file": path.name,
                    "provenance": "Independent PDF vector table and text extraction; no OCR inputs.",
                    "native_control_columns": mapping,
                    "rows": rows,
                }
            )
    codes = {row["discipline_code"] for row in all_rows if row["discipline_code"]}
    for row in all_rows:
        code = row["discipline_code"]
        has_children = code and any(other.startswith(code + ".") for other in codes)
        row["row_type"] = "summary" if not code else "section" if has_children else "discipline"
        row["semesters"] = {
            kind: semester_list(raw) if row["row_type"] == "discipline" else []
            for kind, raw in row["controls"].items()
        }
    return pages


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    pages = extract_native_gt(args.pdf)
    args.output.mkdir(parents=True, exist_ok=True)
    for page in pages:
        target = args.output / f"page{page['page']}_native_gt.json"
        target.write_text(json.dumps(page, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "pages": len(pages),
                "rows": sum(len(page["rows"]) for page in pages),
                "source_sha256": pages[0]["source_sha256"] if pages else None,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

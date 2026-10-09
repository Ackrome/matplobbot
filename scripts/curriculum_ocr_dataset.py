"""Export independently detected curriculum cells for isolated OCR runtimes.

This module deliberately has no GT argument and does not read annotations.
The manifest is model input; evaluation belongs to benchmark_curriculum_ocr.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmark_curriculum_ocr import KINDS, _crop, detect_pages  # noqa: E402


def export_dataset(pdf: Path, output: Path, *, chunk_rows: int = 12) -> dict:
    """Write PNG cells/pages and geometric rows without expected OCR answers."""
    import cv2

    if not 1 <= chunk_rows <= 40:
        raise ValueError("chunk_rows must be between 1 and 40")
    output.mkdir(parents=True, exist_ok=True)
    pages = detect_pages(pdf, output, deskew=True)
    manifest = {
        "version": "curriculum-grid-input-1",
        "source_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "coordinate_space": "normalized original page; pixel_bounds refer to deskewed page",
        "gt_used": False,
        "pages": [],
        "rows": [],
    }

    def save(relative, image):
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            raise ValueError("PNG encoding failed")
        path.write_bytes(encoded.tobytes())
        return relative

    for page in pages:
        columns = {0: "discipline_code", 1: "discipline_name", **page["header_mapping"]}
        page_meta = {
            key: value for key, value in page.items() if key not in {"raw", "clean", "rows"}
        }
        page_meta["raw_path"] = save(f"pages/p{page['page']}_raw.png", page["raw"])
        page_meta["clean_path"] = save(f"pages/p{page['page']}_clean.png", page["clean"])
        page_meta["chunks"] = []
        if columns and page["rows"]:
            right = page["xs"][max(columns) + 1]
            page_meta["table_path"] = save(
                f"pages/p{page['page']}_table.png", page["raw"][:, :right]
            )
            for start in range(0, len(page["rows"]), chunk_rows):
                chunk = page["rows"][start : start + chunk_rows]
                top, bottom = chunk[0]["top"], chunk[-1]["bottom"]
                page_meta["chunks"].append(
                    {
                        "path": save(
                            f"chunks/p{page['page']}_{start:03d}.png",
                            page["raw"][top:bottom, :right],
                        ),
                        "row_ids": [row["prediction_id"] for row in chunk],
                        "pixel_bounds": [0, top, right, bottom],
                    }
                )
        manifest["pages"].append(page_meta)
        for row in page["rows"]:
            record = dict(row, cells={})
            for column, field in columns.items():
                gate = page["clean"][
                    row["top"] + 4 : row["bottom"] - 3,
                    page["xs"][column] + 4 : page["xs"][column + 1] - 3,
                ]
                ink = float((gate < 175).sum()) / max(1, gate.size)
                clean = _crop(page, row, column, "clean")
                raw = _crop(page, row, column, "raw")
                stem = f"cells/{row['prediction_id']}/{field}"
                record["cells"][field] = {
                    "clean_path": save(stem + "_clean.png", clean),
                    "raw_path": save(stem + "_raw.png", raw),
                    "shape": list(clean.shape),
                    "ink_fraction": ink,
                    "blank_gate": bool(field in KINDS and ink < 0.005),
                    "numeric_field": field in KINDS,
                }
            manifest["rows"].append(record)
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tesseract", type=Path)
    parser.add_argument("--tessdata", type=Path)
    parser.add_argument("--chunk-rows", type=int, default=12)
    args = parser.parse_args()
    if args.tesseract:
        os.environ["CURRICULUM_TESSERACT_CMD"] = str(args.tesseract)
    if args.tessdata:
        os.environ["TESSDATA_PREFIX"] = str(args.tessdata)
    result = export_dataset(args.pdf, args.output, chunk_rows=args.chunk_rows)
    print(
        json.dumps(
            {
                "rows": len(result["rows"]),
                "pages": len(result["pages"]),
                "manifest": str((args.output / "manifest.json").resolve()),
            }
        )
    )


if __name__ == "__main__":
    main()

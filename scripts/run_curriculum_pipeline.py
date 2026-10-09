"""Run the production name-OCR/numeric-CNN pipeline locally without GT input."""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared_lib.services.curriculum_layout import LAYOUTS  # noqa: E402
from shared_lib.services.curriculum_ocr import parse_scanned_curriculum  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scan-layout", choices=sorted(LAYOUTS))
    parser.add_argument("--tesseract", type=Path)
    parser.add_argument("--tessdata", type=Path)
    args = parser.parse_args()
    if args.tesseract:
        os.environ["CURRICULUM_TESSERACT_CMD"] = str(args.tesseract)
    if args.tessdata:
        os.environ["TESSDATA_PREFIX"] = str(args.tessdata)
    result = parse_scanned_curriculum(args.pdf.read_bytes(), layout_profile=args.scan_layout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {key: value for key, value in result.items() if key not in {"rows", "assessments"}},
            ensure_ascii=False,
        )
    )
    print(json.dumps({"rows": len(result["rows"]), "assessments": len(result["assessments"])}))
    return 0 if result["assessments"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

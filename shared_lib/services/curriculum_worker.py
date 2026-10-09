"""Private subprocess entry point: native table extraction, then scanned-page OCR."""

import argparse
import io
import json
import os
from pathlib import Path


def parse_document(content: bytes, *, scan_layout: str | None = None) -> dict:
    """Merge text and scanned pages; every OCR result remains a review candidate."""
    import pdfplumber

    from shared_lib.services.curriculum_documents import (
        MAX_ASSESSMENTS,
        MAX_DOCUMENT_PAGES,
        parse_curriculum_pdf,
    )

    result = parse_curriculum_pdf(content)
    result.update({"method": "text", "engine_version": "pdfplumber"})
    if not 1 <= result.get("page_count", 0) <= MAX_DOCUMENT_PAGES:
        return result
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        scanned = [
            number
            for number, page in enumerate(pdf.pages, 1)
            if page.images
            and (
                len(page.chars) < 20
                or any(
                    max(0, image.get("x1", 0) - image.get("x0", 0))
                    * max(0, image.get("bottom", 0) - image.get("top", 0))
                    > page.width * page.height * 0.5
                    for image in page.images
                )
            )
        ]
    if not scanned:
        return result
    from shared_lib.services.curriculum_ocr import parse_scanned_curriculum

    ocr = parse_scanned_curriculum(content, page_numbers=scanned, layout_profile=scan_layout)
    # Text overlays on scanned pages can yield the same fact under printed and
    # synthetic identities. The selected scan parser owns these pages entirely.
    native = [row for row in result["assessments"] if row["page"] not in scanned]
    identities = {
        (row["discipline_code"], row["discipline_name"], row["semester"], row["kind"], row["page"])
        for row in native
    }
    result["assessments"] = native + [
        row
        for row in ocr.get("assessments", [])
        if (
            row["discipline_code"],
            row["discipline_name"],
            row["semester"],
            row["kind"],
            row["page"],
        )
        not in identities
    ]
    if len(result["assessments"]) > MAX_ASSESSMENTS:
        result["assessments"] = []
        result["warnings"].append("The document exceeds the assessment record limit.")
    result["method"] = "mixed" if native else "ocr"
    result["engine_version"] = ocr.get("engine_version", "tesseract")
    result["status"] = "needs_review"
    result["warnings"] = list(
        dict.fromkeys(
            [
                warning
                for warning in result["warnings"]
                if "scanned or blank page" not in warning and "No unambiguous" not in warning
            ]
            + ocr.get("warnings", [])
        )
    )[:100]
    return result


def main():
    from shared_lib.services.curriculum_processing import (
        MAX_RESULT_BYTES,
        SUPPORTED_SCAN_LAYOUTS,
        parse_memory_mb,
        parse_timeout_seconds,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--scan-layout", choices=sorted(SUPPORTED_SCAN_LAYOUTS))
    args = parser.parse_args()

    if os.name == "posix":
        import resource

        memory = parse_memory_mb() * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(
            resource.RLIMIT_CPU, (parse_timeout_seconds(), parse_timeout_seconds() + 1)
        )
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_RESULT_BYTES, MAX_RESULT_BYTES))
    from shared_lib.services.curriculum_documents import MAX_DOCUMENT_BYTES

    source, target = args.source, args.target
    if source.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError("PDF limit")
    result = parse_document(source.read_bytes(), scan_layout=args.scan_layout)
    encoded = json.dumps(result, ensure_ascii=False).encode("utf-8")
    if len(encoded) > MAX_RESULT_BYTES:
        raise ValueError("Result limit")
    target.write_bytes(encoded)


if __name__ == "__main__":
    main()

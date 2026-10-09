"""Name OCR + synthetic-trained numeric CNN, with declared column semantics."""

from __future__ import annotations

import hashlib
import math
import re
import time

from . import curriculum_ocr as raster
from .curriculum_control_cells import read_control_cell
from .curriculum_documents import _SECTION, MAX_DOCUMENT_BYTES, _semester_numbers
from .curriculum_layout import LAYOUT_VERSION, resolve_layout, validate_grid

PIPELINE_VERSION = "fa-name-numeric-1"
CONTROL_FIELDS = ("exam", "pass", "graded_pass", "coursework", "course_project")


def clean_name(value):
    """Normalize display wraps/artifacts without dictionary-driven word guessing."""
    value = re.sub(r"\s+[=|_~]+$", "", value).strip()
    # A space after a hyphen can be grammatical ("микро- и макроэкономики").
    # The OCR strip no longer knows whether it was a printed line break, so
    # never join such words automatically.
    return re.sub(r"\s+", " ", value)


def _original_bbox(box, shape, angle):
    import cv2
    import numpy as np

    height, width = shape
    inverse = cv2.invertAffineTransform(cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1))
    x0, y0, x1, y1 = box
    points = np.array([[x0, y0, 1], [x1, y0, 1], [x1, y1, 1], [x0, y1, 1]]) @ inverse.T
    return [
        round(float(max(0, points[:, 0].min()) / width), 6),
        round(float(max(0, points[:, 1].min()) / height), 6),
        round(float(min(width, points[:, 0].max()) / width), 6),
        round(float(min(height, points[:, 1].max()) / height), 6),
    ]


def parse_page(image, number, layout, numeric, *, deadline):
    """Extract every physical row; only the name column is sent to Tesseract."""
    import numpy as np

    image, angle = raster._deskew(image)
    xs, ys, clean = raster._grid(image)
    # A continuation containing only totals/no grid has no discipline evidence.
    if len(xs) < 6 or len(ys) < 4:
        return [], [], [f"Page {number}: no supported ruled table was found."]
    start = validate_grid(xs, ys, image.shape, layout)
    bounds = [(a, b) for a, b in zip(ys[start:], ys[start + 1 :]) if b - a >= 12]
    if len(bounds) > 200:
        raise ValueError("scan_row_limit: more than 200 physical rows on one page.")
    if not bounds:
        return [], [], [f"Page {number}: no table data rows."]

    def cell(column, top, bottom, *, raw=False):
        source = image if raw else clean
        return source[top + 4 : bottom - 3, xs[column] + 4 : xs[column + 1] - 3]

    # Exactly one OCR batch per page. No header, index, department or numeric OCR.
    names = raster._batch_cells([cell(layout.name_column, a, b) for a, b in bounds])
    backgrounds = [
        float(
            np.median(
                np.concatenate(
                    [cell(c, a, b, raw=True).reshape(-1) for c in layout.context_columns]
                )
            )
        )
        for a, b in bounds
    ]
    paper = float(np.percentile(backgrounds, 85))
    right = xs[max(c for c, _ in layout.controls) + 1]
    rows, records, warnings = [], [], []
    for index, ((top, bottom), name_reading, background) in enumerate(
        zip(bounds, names, backgrounds), 1
    ):
        if time.monotonic() >= deadline:
            raise raster.OcrUnavailable("ocr_timeout: numeric pipeline exceeded its time budget.")
        source_row = f"p{number}_r{index:03d}"
        name = clean_name(name_reading["text"])
        shaded = background < paper - 15
        department = cell(layout.context_columns[0], top, bottom)
        department_ink = float((department < 150).mean()) if department.size else 0
        department_pixels = int((department < 150).sum())
        section_title = bool(_SECTION.match(name))
        # Shaded parent rows contain COUNTS, not semester numbers. White leaf
        # rows have a department value in these declared FA templates. Its text
        # is irrelevant and is never recognized. No printed index is required.
        is_discipline = bool(name and not shaded and not section_title and department_pixels >= 8)
        box = (xs[0], top, right, bottom)
        bbox = _original_bbox(box, image.shape, angle)
        row = {
            "source_row": source_row,
            "prediction_id": source_row,
            "page": number,
            "bbox": bbox,
            "discipline_name": name,
            "is_discipline": is_discipline,
            "row_evidence": {
                "shaded": shaded,
                "background": background,
                "paper": paper,
                "department_ink_fraction": department_ink,
                "department_ink_pixels": department_pixels,
            },
            "cells": {"discipline_name": dict(name_reading, text=name)},
            "layout_profile": layout.name,
        }
        rows.append(row)
        if not is_discipline and not shaded and not section_title:
            warnings.append(f"Page {number}, row {index}: discipline row could not be established.")
        for column, kind in layout.controls:
            if not is_discipline:
                row["cells"][kind] = {"text": "", "abstained": True, "reason": "non_discipline_row"}
                continue
            reading = read_control_cell(cell(column, top, bottom), numeric)
            row["cells"][kind] = reading
            if reading.get("abstained"):
                warnings.append(f"Page {number}, row {index}, {kind}: numeric cell unresolved.")
                continue
            semesters = _semester_numbers(reading.get("text", ""), layout.maximum_semester)
            if semesters is None:
                warnings.append(f"Page {number}, row {index}, {kind}: invalid semester sequence.")
                row["cells"][kind] = dict(
                    reading, abstained=True, reason="invalid_semester_sequence"
                )
                continue
            if not semesters:
                continue
            crop = raster._preview(image, box)
            for semester in semesters:
                records.append(
                    {
                        # Backward-compatible storage key, explicitly not a printed
                        # curriculum index. Scope is the source document revision.
                        "discipline_code": f"scan:p{number}:r{index:03d}",
                        "discipline_name": name,
                        "semester": semester,
                        "kind": kind,
                        "page": number,
                        "source_row": source_row,
                        "evidence": f"Page {number}, row {index}: {name} | {kind}: {reading['text']}",
                        "ocr": {
                            "bbox": bbox,
                            "confidence": min(name_reading["confidence"], reading["confidence"]),
                            "name_confidence": name_reading["confidence"],
                            "numeric_confidence": reading["confidence"],
                            "deskew_degrees": round(angle, 3),
                            "page_rotation": 0,
                            "layout_profile": layout.name,
                            "source_row": source_row,
                            "identity_method": "physical_source_row",
                            "review_required": True,
                            "crop_png_base64": crop,
                        },
                    }
                )
    return records, rows, warnings


def parse_scanned_curriculum(content, *, page_numbers=None, layout_profile=None):
    """Bounded PDF pipeline; missing layout/model never invokes legacy OCR."""
    result = {
        "status": "needs_review",
        "assessments": [],
        "rows": [],
        "warnings": [],
        "page_count": 0,
        "method": "ocr",
        "engine_version": PIPELINE_VERSION,
        "index_ocr": False,
        "header_ocr": False,
        "general_ocr_fields": ["discipline_name"],
        "control_engine": "numeric_cnn_ctc",
        "complete": False,
        "gt_used_for_inference": False,
    }
    if (
        not isinstance(content, bytes)
        or not content.startswith(b"%PDF-")
        or len(content) > MAX_DOCUMENT_BYTES
    ):
        result["warnings"] = ["OCR requires a valid PDF no larger than 20 MiB."]
        return result
    source_hash = hashlib.sha256(content).hexdigest()
    result["source_sha256"] = source_hash
    started = time.monotonic()
    deadline = started + raster.MAX_OCR_SECONDS
    token = raster._DEADLINE.set(deadline)
    try:
        import cv2
        import numpy as np
        import pypdfium2

        from .curriculum_numeric import NumericRecognizer

        cv2.setNumThreads(1)
        # Validate pages before resolving a template/model, so a bad request
        # cannot be hidden by an unrelated missing configuration.
        with pypdfium2.PdfDocument(content) as document:
            result["page_count"] = len(document)
            selected = (
                list(range(1, len(document) + 1)) if page_numbers is None else list(page_numbers)
            )
            if (
                not selected
                or len(selected) > raster.MAX_OCR_PAGES
                or any(type(n) is not int or not 1 <= n <= len(document) for n in selected)
            ):
                raise ValueError("OCR page selection is invalid or exceeds the eight-page limit.")
            selected = sorted(set(selected))
            layout = resolve_layout(source_hash, layout_profile)
            result["layout_profile"] = layout.name
            result["engine_version"] += "; " + LAYOUT_VERSION + "; " + layout.name
            numeric = NumericRecognizer()
            result["model_sha256"] = numeric.model_sha256
            for number in selected:
                if time.monotonic() >= deadline:
                    raise raster.OcrUnavailable("ocr_timeout: document time budget exceeded.")
                page = document[number - 1]
                try:
                    width, height = page.get_size()
                    if width <= 0 or height <= 0:
                        raise ValueError("Invalid PDF page dimensions.")
                    scale = min(
                        5,
                        raster.MAX_RENDER_EDGE / max(width, height),
                        math.sqrt(raster.MAX_RENDER_PIXELS / (width * height)),
                    )
                    bitmap = page.render(scale=scale, grayscale=True)
                    try:
                        image = np.asarray(bitmap.to_pil()).copy()
                    finally:
                        bitmap.close()
                finally:
                    page.close()
                records, rows, warnings = parse_page(
                    image, number, layout, numeric, deadline=deadline
                )
                result["assessments"].extend(records)
                result["rows"].extend(rows)
                result["warnings"].extend(warnings)
                if len(result["assessments"]) > raster.MAX_OCR_RECORDS:
                    raise ValueError("OCR exceeded the assessment limit; partial import discarded.")
        total = 0
        for record in result["assessments"]:
            total += len(record["ocr"]["crop_png_base64"])
            if total > raster.MAX_CROPS_BASE64_BYTES:
                record["ocr"]["crop_png_base64"] = ""
        if not result["assessments"]:
            result["warnings"].append("No unambiguous scanned assessment rows were found.")
        result["warnings"] = list(dict.fromkeys(result["warnings"]))[:100]
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["complete"] = True
    except (ImportError, ValueError, raster.OcrUnavailable) as exc:
        result["assessments"], result["rows"] = [], []
        result["warnings"] = [
            str(exc)
            if not isinstance(exc, ImportError)
            else "ocr_unavailable: numeric CPU pipeline dependencies are missing."
        ]
    except Exception:
        result["assessments"], result["rows"] = [], []
        result["warnings"] = [
            "The scanned PDF could not be read safely; no partial import was kept."
        ]
    finally:
        raster._DEADLINE.reset(token)
    return result

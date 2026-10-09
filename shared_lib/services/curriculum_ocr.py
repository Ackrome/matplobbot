"""CPU OCR of ruled curriculum scans; every extracted fact requires review.

Geometry, rather than the order of OCR words, links a discipline to control
columns. This intentionally supports legible ruled FA tables, not arbitrary
unruled photographs. Run it in the bounded import worker, never a web request.
"""

from __future__ import annotations

import base64
import contextvars
import csv
import io
import math
import os
import re
import subprocess
import tempfile
import time

from .curriculum_documents import _SECTION, MAX_DOCUMENT_BYTES, _header_kind, _semester_numbers

MAX_OCR_PAGES = 8
MAX_RENDER_PIXELS = 24_000_000
MAX_RENDER_EDGE = 6000
MAX_OCR_SECONDS = 240
MAX_CALL_SECONDS = 20
MAX_CROP_BYTES = 20 * 1024
MAX_CROPS_BASE64_BYTES = 4 * 1024 * 1024
MAX_OCR_RECORDS = 1000
PARSER_VERSION = "fa-grid-ocr-2"
_DEADLINE = contextvars.ContextVar("curriculum_ocr_deadline", default=None)


class OcrUnavailable(RuntimeError):
    """The required executable/language data is missing or could not finish."""


def _ocr(image, *, psm=6, digits=False):
    """Return word boxes from a bounded Tesseract CLI invocation (no shell)."""
    import cv2

    executable = os.environ.get(
        "CURRICULUM_TESSERACT_CMD", os.environ.get("TESSERACT_CMD", "tesseract")
    )
    remaining = (_DEADLINE.get() or (time.monotonic() + MAX_CALL_SECONDS)) - time.monotonic()
    if remaining <= 0:
        raise OcrUnavailable("ocr_timeout: OCR exceeded its document time budget.")
    with tempfile.TemporaryDirectory(prefix="mpb-curriculum-ocr-") as folder:
        path = os.path.join(folder, "input.png")
        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            raise OcrUnavailable("OCR image could not be encoded.")
        with open(path, "wb") as stream:
            stream.write(encoded.tobytes())
        command = [executable, path, "stdout", "-l", "rus+eng", "--psm", str(psm)]
        if digits:
            command.extend(["-c", "tessedit_char_whitelist=0123456789,;-"])
        command.append("tsv")
        environment = dict(os.environ, OMP_THREAD_LIMIT="1")
        try:
            response = subprocess.run(
                command,
                capture_output=True,
                check=True,
                timeout=min(MAX_CALL_SECONDS, remaining),
                env=environment,
            )
        except subprocess.TimeoutExpired as exc:
            raise OcrUnavailable("ocr_timeout: Tesseract exceeded its time limit.") from exc
        except (OSError, subprocess.SubprocessError) as exc:
            raise OcrUnavailable(
                "ocr_unavailable: Tesseract with rus+eng data is unavailable."
            ) from exc
    if len(response.stdout) > 2_000_000:
        raise OcrUnavailable("OCR output exceeded its size limit.")
    words = []
    # Tesseract TSV writes literal quotation marks in word text; they are not
    # CSV quoting. Default CSV handling can swallow following physical rows.
    for row in csv.DictReader(
        io.StringIO(response.stdout.decode("utf-8", errors="replace")),
        delimiter="\t",
        quoting=csv.QUOTE_NONE,
    ):
        text = row.get("text", "").strip()
        if not text or row.get("level") != "5":
            continue
        try:
            word = {key: int(row[key]) for key in ("left", "top", "width", "height")}
            word.update(text=text, confidence=max(0, min(100, float(row["conf"]))))
        except (KeyError, TypeError, ValueError):
            continue
        words.append(word)
    return words


def _clusters(indices):
    """Collapse adjacent raster pixels into physical grid-line centres."""
    groups = []
    for value in indices:
        if not groups or value - groups[-1][-1] > 3:
            groups.append([int(value)])
        else:
            groups[-1].append(int(value))
    return [int(round(sum(group) / len(group))) for group in groups]


def _deskew(image):
    import cv2
    import numpy as np

    factor = min(1, 1800 / image.shape[1])
    sample = cv2.resize(image, (int(image.shape[1] * factor), int(image.shape[0] * factor)))
    binary = cv2.threshold(sample, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    lines = cv2.HoughLinesP(
        binary,
        1,
        np.pi / 1800,
        threshold=max(100, sample.shape[1] // 8),
        minLineLength=sample.shape[1] // 3,
        maxLineGap=15,
    )
    angles = []
    if lines is not None:
        for x0, y0, x1, y1 in lines[:, 0]:
            angle = math.degrees(math.atan2(int(y1) - int(y0), int(x1) - int(x0)))
            if abs(angle) <= 3:
                angles.append(angle)
    angle = float(np.median(angles)) if angles else 0.0
    if abs(angle) < 0.04:
        return image, 0.0
    h, w = image.shape
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1)
    return cv2.warpAffine(image, matrix, (w, h), borderValue=255), angle


def _grid(image):
    import cv2
    import numpy as np

    height, width = image.shape
    binary = cv2.adaptiveThreshold(
        image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 13
    )
    horizontal = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(30, width // 40), 1))
    )
    vertical = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(30, height // 35))),
    )
    xs = _clusters(np.flatnonzero(np.count_nonzero(vertical, axis=0) > height * 0.22))
    if len(xs) >= 10:
        left, right = xs[0], xs[9]
        ys = _clusters(
            np.flatnonzero(
                np.count_nonzero(horizontal[:, left:right], axis=1) > (right - left) * 0.68
            )
        )
    else:
        ys = _clusters(np.flatnonzero(np.count_nonzero(horizontal, axis=1) > width * 0.50))
    # Remove rule pixels before OCR. Thickening only the detected rule masks
    # avoids turning a thin grid line into an OCR digit "1".
    mask = cv2.dilate(cv2.bitwise_or(horizontal, vertical), np.ones((3, 3), np.uint8))
    clean = image.copy()
    clean[mask != 0] = 255
    return xs, ys, clean


def _batch_cells(cells, *, digits=False):
    """OCR a padded vertical strip, mapping words back to exact source cells."""
    import cv2
    import numpy as np

    if not cells:
        return []
    slots = []
    y = 12
    prepared = []
    max_width = 0
    for cell in cells:
        h, w = cell.shape
        scale = min(3, max(1, 42 / max(h, 1)))
        enlarged = cv2.resize(
            cell, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_CUBIC
        )
        # A 28px gap keeps wrapped names within their own physical row.
        prepared.append(enlarged)
        slots.append((y, y + enlarged.shape[0]))
        y += enlarged.shape[0] + 28
        max_width = max(max_width, enlarged.shape[1])
    if y * (max_width + 24) > MAX_RENDER_PIXELS:
        raise OcrUnavailable("OCR cell strip exceeds the pixel limit.")
    strip = np.full((y, max_width + 24), 255, dtype=np.uint8)
    for cell, (top, bottom) in zip(prepared, slots):
        strip[top:bottom, 12 : 12 + cell.shape[1]] = cell
    words = _ocr(strip, digits=digits)
    output = []
    for top, bottom in slots:
        selected = [w for w in words if top <= w["top"] + w["height"] / 2 < bottom]
        output.append(
            {
                "text": " ".join(w["text"] for w in selected).strip(),
                "confidence": round(min((w["confidence"] for w in selected), default=0), 1),
            }
        )
    return output


def _code(value):
    clean = re.sub(r"\s+", "", value).replace(",", ".").strip(".|:")
    clean = re.sub(r"^[BБбб6](?=[.1-9])", "Б", clean)
    return clean if re.fullmatch(r"(?:Б\.?\d|ФТД)(?:\.[А-ЯA-Z]{1,3}|\.\d{1,3})+", clean) else None


def _header_mapping(image, xs, header_top, data_top):
    """Recognize rotated labels independently; never infer their order."""
    import cv2

    height = data_top - header_top
    title_crop = image[header_top + 5 : header_top + int(height * 0.25), xs[0] + 5 : xs[2] - 5]
    title = " ".join(word["text"] for word in _ocr(title_crop))
    if "наименован" not in title.casefold() and "discipline" not in title.casefold():
        return {}, "The merged discipline-name header could not be read."
    indices, cells = [], []
    for column in range(2, min(len(xs) - 1, 20)):
        if xs[column] > image.shape[1] * 0.46:
            break
        if xs[column + 1] - xs[column] > image.shape[1] * 0.065:
            continue
        cell = image[
            header_top + int(height * 0.34) : data_top - 5, xs[column] + 5 : xs[column + 1] - 5
        ]
        if cell.size:
            cells.append(cv2.rotate(cell, cv2.ROTATE_90_CLOCKWISE))
            indices.append(column)
    mapping = {}
    recognized = _batch_cells(cells)
    for column, value in zip(indices, recognized):
        kind = _header_kind(value["text"])
        if kind:
            if kind in mapping.values():
                return {}, "Repeated assessment headers have ambiguous geometry."
            mapping[column] = kind
    if len(mapping) < 2:
        return {}, "Fewer than two assessment headers could be read reliably."
    return mapping, None


def _preview(image, bbox):
    import cv2

    x0, y0, x1, y1 = bbox
    crop = image[y0:y1, x0:x1]
    if crop.size == 0:
        return ""
    for width in (1200, 900, 650, 450):
        factor = min(1, width / crop.shape[1])
        resized = cv2.resize(
            crop, (max(1, int(crop.shape[1] * factor)), max(1, int(crop.shape[0] * factor)))
        )
        ok, data = cv2.imencode(".png", resized, [cv2.IMWRITE_PNG_COMPRESSION, 9])
        if ok and len(data) <= MAX_CROP_BYTES:
            return base64.b64encode(data.tobytes()).decode("ascii")
    return ""


def _page_records(image, number):
    """Extract candidates from one deskewed page using physical row boundaries."""
    image, skew = _deskew(image)
    xs, ys, clean = _grid(image)
    if len(xs) < 6 or len(ys) < 4:
        return [], [f"Page {number}: a reliable ruled grid was not found."]
    # The FA assessment header is the first tall row in the full-width grid.
    header = next(
        (i for i in range(min(4, len(ys) - 1)) if ys[i + 1] - ys[i] > image.shape[0] * 0.07), None
    )
    if header is None:
        return [], [f"Page {number}: a separate assessment header was not found."]
    header_top = ys[max(0, header - 1)]
    mapping, error = _header_mapping(clean, xs, header_top, ys[header + 1])
    if error:
        return [], [f"Page {number}: {error}"]
    row_bounds = [(a, b) for a, b in zip(ys[header + 1 :], ys[header + 2 :]) if b - a >= 12]
    if len(row_bounds) > 200:
        return [], [f"Page {number}: the row limit was exceeded."]

    def cells(column):
        return [clean[a + 4 : b - 3, xs[column] + 4 : xs[column + 1] - 3] for a, b in row_bounds]

    codes = _batch_cells(cells(0))
    names = _batch_cells(cells(1))
    if sum(_code(c["text"]) is not None for c in codes) < 2:
        return [], [f"Page {number}: discipline codes do not align with the name header."]
    controls = {column: _batch_cells(cells(column), digits=True) for column in mapping}
    records, warnings = [], []
    all_codes = {_code(c["text"]) for c in codes} - {None}
    for index, (top, bottom) in enumerate(row_bounds):
        code, raw_name = _code(codes[index]["text"]), names[index]["text"]
        name = re.sub(r"\s+[=|_~]+$", "", raw_name).strip()
        if code is None or not name or _SECTION.match(name):
            continue
        if any(other.startswith(code + ".") for other in all_codes):
            continue
        for column, kind in mapping.items():
            reading = controls[column][index]
            value = reading["text"]
            # A nonempty cell that OCR omitted must remain explicitly unresolved.
            raw = cells(column)[index]
            import cv2

            ink = cv2.threshold(raw, 175, 255, cv2.THRESH_BINARY_INV)[1]
            ink_fraction = float((ink != 0).sum()) / max(1, ink.size)
            if not value:
                if 0.015 < ink_fraction < 0.55:
                    warnings.append(f"Page {number}: {code}, {kind}: unreadable nonempty cell.")
                continue
            if ink_fraction < 0.005:
                # Tesseract can hallucinate "1" even on a completely blank
                # cell in a tall strip. Require physical ink, not just output.
                continue
            semesters = _semester_numbers(value, 9)
            if not semesters:
                warnings.append(
                    f"Page {number}: {code}, {kind}: ambiguous semester {value[:30]!r}."
                )
                continue
            bbox = (xs[0], top, xs[max(mapping) + 1], bottom)
            crop = _preview(image, bbox)
            confidence = min(
                codes[index]["confidence"], names[index]["confidence"], reading["confidence"]
            )
            for semester in semesters:
                records.append(
                    {
                        "discipline_code": code,
                        "discipline_name": name,
                        "semester": semester,
                        "kind": kind,
                        "page": number,
                        "evidence": f"OCR: {code} | {raw_name} | {kind}: {value}",
                        "ocr": {
                            "confidence": confidence,
                            "bbox": [
                                round(bbox[0] / image.shape[1], 6),
                                round(top / image.shape[0], 6),
                                round(bbox[2] / image.shape[1], 6),
                                round(bottom / image.shape[0], 6),
                            ],
                            "page_rotation": 0,
                            "deskew_degrees": round(skew, 3),
                            "review_required": True,
                            "crop_png_base64": crop,
                        },
                    }
                )
    return records, warnings


def parse_scanned_curriculum_legacy(
    content: bytes, *, page_numbers: list[int] | None = None
) -> dict:
    """Return bounded OCR candidates and source crops, always ``needs_review``.

    ``page_numbers`` is a one-based subset for mixed text/scanned PDFs. A cap,
    timeout or missing engine never masquerades as a completely parsed document.
    """
    result = {
        "status": "needs_review",
        "assessments": [],
        "warnings": [],
        "page_count": 0,
        "method": "ocr",
        "engine_version": PARSER_VERSION,
    }
    if (
        not isinstance(content, bytes)
        or not content.startswith(b"%PDF-")
        or len(content) > MAX_DOCUMENT_BYTES
    ):
        result["warnings"] = ["OCR requires a valid PDF no larger than 20 MiB."]
        return result
    started = time.monotonic()
    deadline_token = _DEADLINE.set(started + MAX_OCR_SECONDS)
    try:
        import cv2
        import numpy as np
        import pypdfium2

        cv2.setNumThreads(1)
        executable = os.environ.get(
            "CURRICULUM_TESSERACT_CMD", os.environ.get("TESSERACT_CMD", "tesseract")
        )
        try:
            version = subprocess.run(
                [executable, "--version"], capture_output=True, timeout=5, check=True
            )
            version_line = version.stdout.decode("utf-8", errors="replace").splitlines()[0]
            result["engine_version"] += "; " + re.sub(r"[^a-zA-Z0-9 ._+;-]", "", version_line)[:100]
            model = os.environ.get("CURRICULUM_OCR_MODEL_VERSION", "tessdata-fast-system")
            result["engine_version"] += "; " + re.sub(r"[^a-zA-Z0-9 ._+-]", "", model)[:100]
        except subprocess.TimeoutExpired as exc:
            raise OcrUnavailable(
                "ocr_timeout: Tesseract version check exceeded its time limit."
            ) from exc
        except (OSError, subprocess.SubprocessError, IndexError) as exc:
            raise OcrUnavailable("ocr_unavailable: Tesseract executable is not available.") from exc
        with pypdfium2.PdfDocument(content) as document:
            result["page_count"] = len(document)
            selected = (
                list(range(1, len(document) + 1))
                if page_numbers is None
                else sorted(set(page_numbers))
            )
            if (
                not selected
                or len(selected) > MAX_OCR_PAGES
                or any(type(n) is not int or not 1 <= n <= len(document) for n in selected)
            ):
                result["warnings"] = [
                    "OCR page selection is invalid or exceeds the eight-page limit."
                ]
                return result
            for number in selected:
                if time.monotonic() - started > MAX_OCR_SECONDS:
                    raise OcrUnavailable(
                        "ocr_timeout: OCR exceeded its document time budget; review is incomplete."
                    )
                page = document[number - 1]
                try:
                    width, height = page.get_size()
                    if width <= 0 or height <= 0:
                        raise OcrUnavailable("Invalid PDF page dimensions.")
                    scale = min(
                        5,
                        MAX_RENDER_EDGE / max(width, height),
                        math.sqrt(MAX_RENDER_PIXELS / (width * height)),
                    )
                    bitmap = page.render(scale=scale, grayscale=True)
                    try:
                        image = np.asarray(bitmap.to_pil()).copy()
                    finally:
                        bitmap.close()
                finally:
                    page.close()
                records, warnings = _page_records(image, number)
                result["assessments"].extend(records)
                result["warnings"].extend(warnings)
                if len(result["assessments"]) > MAX_OCR_RECORDS:
                    raise OcrUnavailable(
                        "OCR exceeded the assessment limit; no truncated curriculum was imported."
                    )
        crop_bytes = 0
        for record in result["assessments"]:
            crop = record["ocr"]["crop_png_base64"]
            crop_bytes += len(crop)
            if crop_bytes > MAX_CROPS_BASE64_BYTES:
                record["ocr"]["crop_png_base64"] = ""
        result["warnings"].insert(
            0,
            "OCR candidates require visual review of names, semesters and table cells before publication.",
        )
        if not result["assessments"]:
            result["warnings"].append("No unambiguous scanned assessment rows were found.")
        result["warnings"] = list(dict.fromkeys(result["warnings"]))[:100]
    except (ImportError, OcrUnavailable) as exc:
        result["assessments"] = []
        result["warnings"] = [
            str(exc)
            if isinstance(exc, OcrUnavailable)
            else "ocr_unavailable: CPU OCR dependencies are not installed."
        ]
    except Exception:
        result["assessments"] = []
        result["warnings"] = [
            "The scanned PDF could not be read safely; manual review is required."
        ]
    finally:
        _DEADLINE.reset(deadline_token)
    return result


def parse_scanned_curriculum(
    content: bytes, *, page_numbers: list[int] | None = None, layout_profile: str | None = None
) -> dict:
    """Read names with OCR and control cells with the packaged numeric CNN.

    Printed discipline indices and table headers are never recognized. The
    legacy all-OCR implementation is retained solely for offline comparisons.
    """
    from .curriculum_pipeline import parse_scanned_curriculum as parse

    return parse(content, page_numbers=page_numbers, layout_profile=layout_profile)

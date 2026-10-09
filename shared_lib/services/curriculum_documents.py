"""Bounded official-document downloads and conservative curriculum PDF extraction.

Extraction is evidence for an administrator to review, not proof that a document
belongs to a particular group. No programme/cohort association is inferred here.
"""

from __future__ import annotations

import asyncio
import io
import re
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import aiohttp
import pdfplumber

MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
MAX_DOCUMENT_PAGES = 100
MAX_PAGE_CHARACTERS = 200_000
MAX_TOTAL_CHARACTERS = 1_000_000
MAX_ASSESSMENTS = 5_000
MAX_TABLES_PER_PAGE = 100
_OFFICIAL_HOSTS = {"fa.ru", "www.fa.ru"}
_CODE = re.compile(r"^(?:Б\.?\d|ФТД|B\.?\d)[\w.\-]*$", re.IGNORECASE)
_SECTION = re.compile(
    r"^(?:блок\s|цикл\s|модуль\s|обязательная часть|часть,?\s|итого\b|всего\b|"
    r"факультативы\b|дисциплины по выбору|block\s|module\s|total\b)",
    re.IGNORECASE,
)
_KINDS = {
    "exam": {"экзамен", "экзамены", "экз", "exam", "exams"},
    "pass": {"зачет", "зачеты", "зач", "pass"},
    "graded_pass": {
        "зачетсоценкой",
        "зачетысоценкой",
        "дифференцированныйзачет",
        "зачетсоц",
        "gradedpass",
    },
    "coursework": {"курсоваяработа", "курсовыеработы", "кр", "coursework"},
    "course_project": {"курсовойпроект", "курсовыепроекты", "кп", "courseproject"},
}


class CurriculumDocumentError(ValueError):
    """A document cannot be safely downloaded or is not an official PDF."""


class _ExtractionLimitError(ValueError):
    """Stop the import rather than return a silently truncated curriculum."""


def validate_official_document_url(url: str) -> str:
    """Accept only university-hosted HTTPS upload URLs, including redirects."""
    if not isinstance(url, str) or not url or len(url) > 2048 or re.search(r"[\x00-\x20\x7f]", url):
        raise CurriculumDocumentError("An official HTTPS document URL is required.")
    try:
        parts = urlsplit(url)
        valid = (
            parts.scheme == "https"
            and parts.hostname in _OFFICIAL_HOSTS
            and parts.port in (None, 443)
            and not parts.username
            and not parts.password
        )
    except ValueError as exc:
        raise CurriculumDocumentError("Invalid document URL.") from exc
    path = parts.path
    for _ in range(3):
        path = unquote(path)
    if (
        not valid
        or not path.startswith("/upload/")
        or "\\" in path
        or "%" in path
        or any(segment in (".", "..") for segment in path.split("/"))
        or re.search(r"[\x00-\x1f\x7f]", path)
    ):
        raise CurriculumDocumentError("Only HTTPS documents under fa.ru/upload/ are supported.")
    return urlunsplit(("https", parts.hostname, parts.path, parts.query, ""))


async def fetch_official_document(session: aiohttp.ClientSession, url: str) -> bytes:
    """Fetch a PDF with validated redirects, a 45-second budget and 20 MiB cap."""
    current = validate_official_document_url(url)
    try:
        async with asyncio.timeout(45):
            for redirect in range(4):
                async with session.get(
                    current,
                    allow_redirects=False,
                    timeout=aiohttp.ClientTimeout(total=30, sock_connect=10),
                    headers={
                        "Accept": "application/pdf",
                        "User-Agent": "Matplobbot-Curriculum/1.0",
                    },
                ) as response:
                    if response.status in {301, 302, 303, 307, 308}:
                        location = response.headers.get("Location")
                        if not location or redirect == 3:
                            raise CurriculumDocumentError("Document redirect limit exceeded.")
                        current = validate_official_document_url(urljoin(current, location))
                        continue
                    if response.status != 200:
                        raise CurriculumDocumentError(
                            f"Official document returned HTTP {response.status}."
                        )
                    if response.content_length and response.content_length > MAX_DOCUMENT_BYTES:
                        raise CurriculumDocumentError("Official PDF exceeds the 20 MiB size limit.")
                    data = bytearray()
                    async for chunk in response.content.iter_chunked(64 * 1024):
                        data.extend(chunk)
                        if len(data) > MAX_DOCUMENT_BYTES:
                            raise CurriculumDocumentError(
                                "Official PDF exceeds the 20 MiB size limit."
                            )
                    if not data.startswith(b"%PDF-"):
                        raise CurriculumDocumentError("Official document is not a PDF.")
                    return bytes(data)
    except (aiohttp.ClientError, TimeoutError) as exc:
        raise CurriculumDocumentError("Official document could not be downloaded.") from exc
    raise CurriculumDocumentError("Official PDF was not downloaded.")


def _text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _compact(value: str) -> str:
    return re.sub(r"[^a-zа-я]", "", value.lower().replace("ё", "е"))


def _header_kind(value: str | None) -> str | None:
    # Rotated Russian cells are sometimes extracted bottom-to-top, including
    # split words: 'мен\nЭкза'. Compare both line orders, never numeric positions.
    lines = (value or "").splitlines()
    forms = {_compact("".join(lines)), _compact("".join(reversed(lines)))}
    for kind, aliases in _KINDS.items():
        if forms & aliases:
            return kind
    return None


def _semester_numbers(value: str | None, maximum: int) -> list[int] | None:
    clean = _text(value)
    if not clean or clean in {"-", "—", "–"}:
        return []
    # A compact '78' is ambiguous; a delimited '7,8' is not. Ranges are accepted
    # only when both ends are explicit and within the document's semester range.
    if not re.fullmatch(
        r"\d{1,2}(?:\s*[-–]\s*\d{1,2})?(?:[\s,;]+\d{1,2}(?:\s*[-–]\s*\d{1,2})?)*", clean
    ):
        return None
    result: set[int] = set()
    for token in re.findall(r"\d{1,2}(?:\s*[-–]\s*\d{1,2})?", clean):
        ends = [int(part) for part in re.split(r"\s*[-–]\s*", token)]
        if not 1 <= ends[0] <= ends[-1] <= maximum:
            return None
        result.update(range(ends[0], ends[-1] + 1))
    return sorted(result)


def _table_records(
    table,
    page_number: int,
    maximum_semester: int,
    remaining_assessments: int | None = None,
    *,
    source_codes: set[str] | None = None,
) -> tuple[list[dict], list[str]]:
    """Read only ruled tables whose headers and code/name columns are known."""
    rows = table.extract()
    if not rows:
        return [], []
    first_data = next(
        (i for i, row in enumerate(rows) if any(_CODE.fullmatch(_text(c)) for c in row)), None
    )
    if first_data is None:
        return [], []
    headers = rows[:first_data]
    mapping: dict[int, str] = {}
    for row in headers:
        for column, cell in enumerate(row):
            kind = _header_kind(cell)
            if kind:
                if column in mapping and mapping[column] != kind:
                    return [], [f"Page {page_number}: conflicting assessment column headers."]
                mapping[column] = kind
    if not mapping:
        return [], [f"Page {page_number}: curriculum rows have no readable assessment headers."]
    if len(mapping.values()) != len(set(mapping.values())):
        return [], [f"Page {page_number}: repeated assessment columns need manual review."]
    for column, kind in mapping.items():
        data_cell = table.rows[first_data].cells[column]
        aligned = any(
            column < len(header.cells)
            and header.cells[column]
            and data_cell
            and _header_kind(rows[index][column]) == kind
            and abs(header.cells[column][0] - data_cell[0]) <= 1
            and abs(header.cells[column][2] - data_cell[2]) <= 1
            for index, header in enumerate(table.rows[:first_data])
        )
        if not aligned:
            return [], [f"Page {page_number}: assessment header spans ambiguous columns."]
    code_columns = {
        index
        for row in headers
        for index, cell in enumerate(row)
        if _compact(cell or "")
        in {"индекс", "код", "индексдисциплины", "коддисциплины", "code", "index"}
    }
    name_columns = {
        index
        for row in headers
        for index, cell in enumerate(row)
        if "наименование" in _compact(cell or "")
        or _compact(cell or "") in {"дисциплина", "discipline", "disciplinename", "coursename"}
    }
    if not name_columns:
        return [], [f"Page {page_number}: discipline name header is missing."]
    if len(code_columns) == 1 and len(name_columns) == 1:
        code_column, name_column = next(iter(code_columns)), next(iter(name_columns))
    elif not code_columns and len(name_columns) == 1:
        # FA's wide plans merge 'Наименование ... дисциплин' over two physical
        # columns. Verify that the actual header cell spans both code and name.
        code_column = next(iter(name_columns))
        name_column = code_column + 1
        geometry_ok = any(
            code_column < len(header.cells)
            and header.cells[code_column]
            and name_column < len(header.cells)
            and header.cells[name_column] is None
            and name_column < len(table.rows[first_data].cells)
            and table.rows[first_data].cells[name_column]
            and header.cells[code_column][2] >= table.rows[first_data].cells[name_column][2] - 1
            for header in table.rows[:first_data]
        )
        if not geometry_ok:
            return [], [f"Page {page_number}: merged code/name header is ambiguous."]
    else:
        return [], [f"Page {page_number}: discipline identity columns are ambiguous."]
    if code_column == name_column or name_column in mapping or code_column in mapping:
        return [], [f"Page {page_number}: overlapping curriculum columns."]
    if source_codes is not None:
        # A child with blank assessment cells still makes its ancestor a section.
        # Collect the hierarchy before assessment/section filtering, across pages.
        source_codes.update(
            code
            for row in rows[first_data:]
            if code_column < len(row) and _CODE.fullmatch(code := _text(row[code_column]))
        )
    candidates: list[dict] = []
    warnings: list[str] = []
    limit = MAX_ASSESSMENTS if remaining_assessments is None else remaining_assessments
    for row in rows[first_data:]:
        if max(code_column, name_column, *mapping) >= len(row):
            warnings.append(f"Page {page_number}: incomplete curriculum row.")
            continue
        code, name = _text(row[code_column]), _text(row[name_column])
        if _SECTION.match(name):
            continue
        if not _CODE.fullmatch(code):
            # Ignore repeated header rows and footers; an assessment-bearing
            # unnamed row can be a split discipline and must not be published.
            values = [row[column] for column in mapping]
            if any(re.fullmatch(r"[\d\s,;–-]+", _text(value)) for value in values if _text(value)):
                warnings.append(f"Page {page_number}: assessment row has no discipline code.")
            continue
        if not name or len(name) < 3:
            warnings.append(f"Page {page_number}: {code} has no readable discipline name.")
            continue
        for column, kind in mapping.items():
            semesters = _semester_numbers(row[column], maximum_semester)
            if semesters is None:
                warnings.append(
                    f"Page {page_number}: {code}, {kind}: ambiguous semester cell {_text(row[column])[:60]!r}."
                )
                continue
            for semester in semesters:
                if len(candidates) >= limit:
                    raise _ExtractionLimitError(
                        "The PDF exceeds the assessment record limit; no truncated curriculum was imported."
                    )
                candidates.append(
                    {
                        "discipline_code": code,
                        "discipline_name": name,
                        "semester": semester,
                        "kind": kind,
                        "page": page_number,
                        "evidence": f"{code} | {name} | {kind}: {_text(row[column])}",
                    }
                )
    return candidates, warnings


def parse_curriculum_pdf(content: bytes) -> dict:
    """Extract assessment semesters; unsupported/ambiguous input needs review.

    Returned records are *candidates*. Even ``parsed`` does not confirm the
    group's programme or authorize publishing a new document revision.
    """
    result = {"status": "needs_review", "assessments": [], "warnings": [], "page_count": 0}
    if not isinstance(content, bytes) or not content.startswith(b"%PDF-"):
        result["warnings"] = ["The document is not a PDF."]
        return result
    if len(content) > MAX_DOCUMENT_BYTES:
        result["warnings"] = ["The PDF exceeds the 20 MiB size limit."]
        return result
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            result["page_count"] = len(pdf.pages)
            if not 0 < len(pdf.pages) <= MAX_DOCUMENT_PAGES:
                result["warnings"] = ["The PDF page count is outside the supported range (1–100)."]
                return result
            candidates = []
            warnings = []
            source_codes: set[str] = set()
            total_characters = 0
            for number, page in enumerate(pdf.pages, 1):
                total_characters += len(page.chars)
                if total_characters > MAX_TOTAL_CHARACTERS:
                    raise _ExtractionLimitError(
                        "The PDF exceeds the total character limit; manual review is required."
                    )
                if len(page.chars) > MAX_PAGE_CHARACTERS:
                    warnings.append(f"Page {number}: too many characters for safe extraction.")
                    continue
                if not page.chars:
                    warnings.append(f"Page {number}: scanned or blank page requires manual review.")
                    continue
                page_text = page.extract_text() or ""
                semester_headers = [
                    int(n) for n in re.findall(r"\b(\d{1,2})\s*семестр\b", page_text, re.IGNORECASE)
                ]
                semester_headers.extend(
                    int(n)
                    for n in re.findall(r"\bsemester\s+(\d{1,2})\b", page_text, re.IGNORECASE)
                )
                # A simple assessment-only table may omit semester workload
                # headers. Without them, two-digit values such as '12' might
                # mean semester 12 or undelimited semesters 1 and 2. Neither
                # interpretation is sufficiently supported to publish.
                maximum = max(semester_headers, default=9)
                if maximum > 16:
                    warnings.append(f"Page {number}: unsupported semester numbering.")
                    continue
                tables = page.find_tables()
                if len(tables) > MAX_TABLES_PER_PAGE:
                    raise _ExtractionLimitError(
                        "The PDF exceeds the per-page table limit; manual review is required."
                    )
                if not tables and re.search(
                    r"(?:зач[её]т|экзамен|assessment)", page_text, re.IGNORECASE
                ):
                    warnings.append(
                        f"Page {number}: assessment text has no reliable table geometry."
                    )
                for table in tables:
                    records, table_warnings = _table_records(
                        table,
                        number,
                        maximum,
                        MAX_ASSESSMENTS - len(candidates),
                        source_codes=source_codes,
                    )
                    candidates.extend(records)
                    warnings.extend(table_warnings)
            # A parent row can contain totals, not semester identifiers. Drop
            # it even when a short total such as '3' happens to look plausible.
            parents = {
                code[:separator]
                for code in source_codes
                for separator, character in enumerate(code)
                if character == "." and code[:separator] in source_codes
            }
            seen = set()
            names: dict[str, set[str]] = {}
            for record in candidates:
                code = record["discipline_code"]
                if code in parents:
                    continue
                names.setdefault(code, set()).add(record["discipline_name"].casefold())
                key = (code, record["discipline_name"], record["semester"], record["kind"])
                if key not in seen:
                    result["assessments"].append(record)
                    seen.add(key)
            if any(len(values) > 1 for values in names.values()):
                warnings.append(
                    "The same discipline code has different names; review document editions."
                )
            if not result["assessments"]:
                warnings.append("No unambiguous discipline assessment rows were found.")
            result["warnings"] = list(dict.fromkeys(warnings))[:100]
            if result["assessments"] and not result["warnings"]:
                result["status"] = "parsed"
    except _ExtractionLimitError as exc:
        result["assessments"] = []
        result["warnings"] = [str(exc)]
    except Exception:
        # Parser failures are an import state, never evidence of no exam. Avoid
        # exposing PDF internals or arbitrary document strings in API errors.
        result["assessments"] = []
        result["warnings"] = ["The PDF could not be read safely; manual review is required."]
    return result

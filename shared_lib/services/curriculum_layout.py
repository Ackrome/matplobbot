"""Declared FA table layouts: column semantics without header/index OCR."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TableLayout:
    name: str
    controls: tuple[tuple[int, str], ...]
    name_column: int = 1
    context_columns: tuple[int, ...] = (2, 3)
    maximum_semester: int = 16


LAYOUT_VERSION = "fa-declared-grid-1"
LAYOUTS = {
    "fa_legacy_v1": TableLayout(
        "fa_legacy_v1",
        (
            (4, "exam"),
            (5, "pass"),
            (6, "coursework"),
            (7, "course_project"),
            (9, "graded_pass"),
        ),
    ),
    "fa_compact_v1": TableLayout(
        "fa_compact_v1",
        (
            (4, "exam"),
            (5, "pass"),
            (6, "graded_pass"),
            (7, "coursework"),
            (8, "course_project"),
        ),
    ),
}
# These source layouts were visually checked, independently of OCR/GT values.
# A changed PDF must declare its layout; year/name alone cannot identify columns.
KNOWN_SOURCE_LAYOUTS = {
    "73d6fa541ce75445d21d3e6ed810ee532954959056f6d9cf314e0f84fcd94bf3": "fa_legacy_v1",
    "26aa4732da0efe213f5e2426ce63c85c04ab15a854c1542c4264d5d4c9239b86": "fa_compact_v1",
}


def resolve_layout(source_sha256: str, requested: str | None = None) -> TableLayout:
    """Use an explicit declaration or a verified source, never guessed semantics."""
    known = KNOWN_SOURCE_LAYOUTS.get(source_sha256)
    selected = requested or known
    if selected not in LAYOUTS:
        raise ValueError("scan_layout_required: choose a verified table layout for this PDF.")
    if requested and known and requested != known:
        raise ValueError(
            "scan_layout_conflict: declared columns disagree with the verified source."
        )
    return LAYOUTS[selected]


def validate_grid(xs, ys, shape, layout: TableLayout) -> int:
    """Reject missing/shifted columns; return the geometric bottom of the header.

    The two layouts are deliberately NOT distinguished by these similar widths.
    This check validates a declared template, not the meaning of printed labels.
    """
    height, width = shape
    last = max(column for column, _ in layout.controls)
    if len(xs) <= last + 1 or len(ys) < 4:
        raise ValueError("scan_grid_mismatch: incomplete ruled table.")
    if any(b <= a for a, b in zip(xs, xs[1:])) or any(b <= a for a, b in zip(ys, ys[1:])):
        raise ValueError("scan_grid_mismatch: grid boundaries are not increasing.")
    name_width = xs[2] - xs[1]
    if not 0.05 * width < name_width < 0.18 * width:
        raise ValueError("scan_grid_mismatch: discipline-name column has unexpected width.")
    expected = (0, 0.33, 1.33, 1.65, 1.99, 2.14, 2.28, 2.41, 2.55, 2.68, 2.81)
    normalized = [(x - xs[0]) / name_width for x in xs[: len(expected)]]
    if any(abs(actual - target) > 0.09 for actual, target in zip(normalized, expected)):
        raise ValueError("scan_grid_mismatch: declared columns do not match the physical grid.")
    header = next(
        (i for i in range(min(4, len(ys) - 1)) if ys[i + 1] - ys[i] > height * 0.07), None
    )
    if header is None:
        raise ValueError("scan_grid_mismatch: table header boundary was not found.")
    return header + 1

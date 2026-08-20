"""Build the filtered requirements file consumed by the dependency audit gate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_REQUIREMENT_FILES = (
    Path("requirements.txt"),
    Path("fastapi_stats_app/requirements.txt"),
    Path("scheduler_app/requirements.txt"),
)
DEFAULT_EXCLUDED_PACKAGES = {"matplobbot-shared"}
DEFAULT_OUTPUT = Path("audit-requirements.txt")
EDITABLE_PREFIXES = ("-e ", "--editable ")
UNSUPPORTED_PREFIXES = ("-r ", "--requirement ", "-c ", "--constraint ")
SPECIFIERS = ("===", "==", "~=", "!=", ">=", "<=", ">", "<")


def _canonical_name(name: str) -> str:
    return name.replace("_", "-").lower()


def _strip_inline_comment(line: str) -> str:
    comment_index = line.find(" #")
    if comment_index == -1:
        return line.strip()
    return line[:comment_index].strip()


def _requirement_name(line: str) -> str:
    requirement = line.split(";", 1)[0].strip()
    if " @ " in requirement:
        return _canonical_name(requirement.split(" @ ", 1)[0].strip())

    split_at = len(requirement)
    for specifier in SPECIFIERS:
        index = requirement.find(specifier)
        if index != -1:
            split_at = min(split_at, index)

    name = requirement[:split_at].split("[", 1)[0].strip()
    return _canonical_name(name)


def build_audit_requirements(
    requirement_files: list[Path],
    output_path: Path,
    excluded_packages: set[str] | None = None,
) -> list[str]:
    """Write a deduplicated audit requirements file and return its lines."""

    excluded = {_canonical_name(package) for package in (excluded_packages or set())}
    by_package: dict[str, str] = {}
    ordered_lines: list[str] = []

    for req_path in requirement_files:
        for line_number, raw_line in enumerate(req_path.read_text(encoding="utf-8").splitlines(), 1):
            line = _strip_inline_comment(raw_line.strip())
            if not line or line.startswith("#"):
                continue

            lower = line.lower()
            if lower.startswith(EDITABLE_PREFIXES):
                continue
            if lower.startswith(UNSUPPORTED_PREFIXES):
                raise ValueError(
                    f"{req_path}:{line_number}: expand nested requirements before auditing: {line}"
                )
            if lower.startswith("-"):
                raise ValueError(
                    f"{req_path}:{line_number}: unsupported pip option in audit input: {line}"
                )

            package_name = _requirement_name(line)
            if not package_name:
                raise ValueError(f"{req_path}:{line_number}: cannot parse requirement: {line}")
            if package_name in excluded:
                continue

            existing = by_package.get(package_name)
            if existing is None:
                by_package[package_name] = line
                ordered_lines.append(line)
            elif existing != line:
                raise ValueError(
                    f"{req_path}:{line_number}: conflicting audit pins for {package_name}: "
                    f"{existing!r} vs {line!r}"
                )

    output_path.write_text("\n".join(ordered_lines) + "\n", encoding="utf-8")
    return ordered_lines


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the filtered requirements file used by pip-audit."
    )
    parser.add_argument(
        "-r",
        "--requirement",
        action="append",
        type=Path,
        default=None,
        help="Requirements file to include. Defaults to project runtime requirement files.",
    )
    parser.add_argument(
        "--exclude-package",
        action="append",
        default=sorted(DEFAULT_EXCLUDED_PACKAGES),
        help="Package name to exclude from the audit input, for local in-repo packages.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Filtered requirements output path.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    requirement_files = args.requirement or list(DEFAULT_REQUIREMENT_FILES)
    lines = build_audit_requirements(
        requirement_files=requirement_files,
        output_path=args.output,
        excluded_packages=set(args.exclude_package),
    )
    print(f"Prepared {len(lines)} packages for security audit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

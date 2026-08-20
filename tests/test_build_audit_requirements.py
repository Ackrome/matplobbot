from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_audit_requirements.py"
SPEC = importlib.util.spec_from_file_location("build_audit_requirements", SCRIPT_PATH)
assert SPEC is not None
build_audit_requirements_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_audit_requirements_module)


class TestBuildAuditRequirements(unittest.TestCase):
    def test_builds_deduplicated_filtered_requirements(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            first = root / "requirements.txt"
            second = root / "service-requirements.txt"
            output = root / "audit-requirements.txt"

            first.write_text(
                "\n".join(
                    [
                        "# ignored comment",
                        "aiohttp==3.14.3",
                        "matplobbot-shared==0.1.318",
                        "-e .",
                        "sqlalchemy[asyncio]==2.0.36  # inline comment",
                    ]
                ),
                encoding="utf-8",
            )
            second.write_text(
                "\n".join(
                    [
                        "aiohttp==3.14.3",
                        "fastapi==0.136.3",
                    ]
                ),
                encoding="utf-8",
            )

            lines = build_audit_requirements_module.build_audit_requirements(
                requirement_files=[first, second],
                output_path=output,
                excluded_packages={"matplobbot-shared"},
            )

            self.assertEqual(
                lines,
                [
                    "aiohttp==3.14.3",
                    "sqlalchemy[asyncio]==2.0.36",
                    "fastapi==0.136.3",
                ],
            )
            self.assertEqual(output.read_text(encoding="utf-8"), "\n".join(lines) + "\n")

    def test_conflicting_pins_fail_closed(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            first = root / "requirements.txt"
            second = root / "service-requirements.txt"
            output = root / "audit-requirements.txt"

            first.write_text("aiohttp==3.14.2\n", encoding="utf-8")
            second.write_text("aiohttp==3.14.3\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "conflicting audit pins for aiohttp"):
                build_audit_requirements_module.build_audit_requirements(
                    requirement_files=[first, second],
                    output_path=output,
                    excluded_packages=set(),
                )


if __name__ == "__main__":
    unittest.main()

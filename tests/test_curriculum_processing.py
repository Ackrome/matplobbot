"""Subprocess isolation and native/mixed PDF dispatch without an installed OCR engine."""

import asyncio
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from shared_lib.services import curriculum_processing as runtime
from shared_lib.services.curriculum_worker import parse_document
from tests.test_curriculum_documents import HEADERS, synthetic_pdf


class TestCurriculumWorker(unittest.IsolatedAsyncioTestCase):
    async def test_real_child_process_parses_text_and_cleans_temporary_files(self):
        content = synthetic_pdf([HEADERS, ["B1.01", "Machine learning", "7", "", "", "", ""]])
        original_create = asyncio.create_subprocess_exec
        calls = []

        async def capture(*args, **kwargs):
            calls.append((args, kwargs))
            return await original_create(*args, **kwargs)

        with patch.object(runtime.asyncio, "create_subprocess_exec", capture):
            result = await runtime.parse_document_in_worker(content)
        self.assertEqual(result["method"], "text")
        self.assertEqual(result["assessments"][0]["semester"], 7)
        args, kwargs = calls[0]
        self.assertFalse(Path(args[-2]).exists())
        self.assertFalse(Path(args[-1]).exists())
        self.assertEqual(kwargs["env"]["CUDA_VISIBLE_DEVICES"], "")
        self.assertEqual(kwargs["env"]["OMP_THREAD_LIMIT"], "1")

    async def test_timeout_kills_child_and_returns_safe_code(self):
        original_create = asyncio.create_subprocess_exec
        children = []

        async def hanging_worker(*args, **kwargs):
            if args[0] == sys.executable:
                process = await original_create(
                    sys.executable, "-c", "import time; time.sleep(60)", **kwargs
                )
                children.append(process)
                return process
            return await original_create(*args, **kwargs)  # Windows taskkill

        with (
            patch.object(runtime.asyncio, "create_subprocess_exec", hanging_worker),
            patch.object(runtime, "parse_timeout_seconds", return_value=0.1),
        ):
            with self.assertRaisesRegex(runtime.CurriculumProcessingError, "^parse_timeout$"):
                await runtime.parse_document_in_worker(b"%PDF-test")
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].returncode)

    async def test_cancelled_parent_terminates_worker(self):
        process = SimpleNamespace(pid=12345, wait=AsyncMock(side_effect=asyncio.CancelledError()))
        with (
            patch.object(
                runtime.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
            ),
            patch.object(runtime, "_terminate", AsyncMock()) as terminate,
        ):
            with self.assertRaises(asyncio.CancelledError):
                await runtime.parse_document_in_worker(b"%PDF-test")
        terminate.assert_awaited_once_with(process)

    def test_configuration_is_bounded_and_model_cache_key_changes(self):
        with patch.dict(
            os.environ,
            {"CURRICULUM_PARSE_TIMEOUT_SECONDS": "9999", "CURRICULUM_PARSE_MEMORY_MB": "0"},
        ):
            self.assertEqual(runtime.parse_timeout_seconds(), 600)
            self.assertEqual(runtime.parse_memory_mb(), 512)
        with patch.dict(os.environ, {"CURRICULUM_PARSE_TIMEOUT_SECONDS": "invalid"}):
            self.assertEqual(runtime.parse_timeout_seconds(), 300)
        old = runtime.current_parser_version()
        with patch.dict(os.environ, {"CURRICULUM_OCR_MODEL_VERSION": "different-model-build"}):
            self.assertNotEqual(runtime.current_parser_version(), old)
        self.assertNotEqual(
            runtime.current_parser_version("fa_legacy_v1"),
            runtime.current_parser_version("fa_compact_v1"),
        )
        with self.assertRaises(ValueError):
            runtime.current_parser_version("unknown")

    async def test_invalid_scan_layout_is_rejected_before_spawning(self):
        with patch.object(runtime.asyncio, "create_subprocess_exec", AsyncMock()) as spawn:
            with self.assertRaises(ValueError):
                await runtime.parse_document_in_worker(b"%PDF-test", scan_layout="bad;command")
        spawn.assert_not_awaited()

    async def test_explicit_scan_layout_survives_real_worker_cli(self):
        content = synthetic_pdf([HEADERS, ["B1.01", "Math", "7", "", "", "", ""]])
        result = await runtime.parse_document_in_worker(content, scan_layout="fa_compact_v1")
        self.assertEqual(result["method"], "text")
        self.assertEqual(result["assessments"][0]["semester"], 7)

    def test_mixed_pdf_keeps_native_rows_and_dispatches_only_scanned_pages(self):
        native = {
            "discipline_code": "B1.01",
            "discipline_name": "Math",
            "semester": 1,
            "kind": "exam",
            "page": 1,
            "evidence": "Exam 1",
        }
        scanned = {
            **native,
            "discipline_name": "Physics",
            "discipline_code": "B1.02",
            "page": 2,
            "ocr": {"review_required": True},
        }
        pages = [
            SimpleNamespace(chars=[{}] * 100, images=[], width=100, height=100),
            # A scan with a text watermark still needs OCR.
            SimpleNamespace(
                chars=[{}] * 80,
                images=[{"x0": 0, "x1": 100, "top": 0, "bottom": 100}],
                width=100,
                height=100,
            ),
        ]
        opened = MagicMock()
        opened.__enter__.return_value.pages = pages
        with (
            patch(
                "shared_lib.services.curriculum_documents.parse_curriculum_pdf",
                return_value={
                    "status": "needs_review",
                    "assessments": [native],
                    "page_count": 2,
                    "warnings": ["Page 2: scanned or blank page requires manual review."],
                },
            ),
            patch("pdfplumber.open", return_value=opened),
            patch(
                "shared_lib.services.curriculum_ocr.parse_scanned_curriculum",
                return_value={
                    "assessments": [scanned],
                    "warnings": ["Verify OCR"],
                    "engine_version": "Tesseract 5",
                },
            ) as ocr,
        ):
            result = parse_document(b"%PDF-fixture")
        ocr.assert_called_once_with(b"%PDF-fixture", page_numbers=[2], layout_profile=None)
        self.assertEqual(result["method"], "mixed")
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["assessments"], [native, scanned])
        self.assertEqual(result["warnings"], ["Verify OCR"])

    def test_scan_overlay_native_rows_do_not_duplicate_physical_identities(self):
        native = {
            "discipline_code": "B1.01",
            "discipline_name": "Math",
            "semester": 7,
            "kind": "exam",
            "page": 1,
            "evidence": "Exam 7",
        }
        scan = {**native, "discipline_code": "scan:p1:r001"}
        opened = MagicMock()
        opened.__enter__.return_value.pages = [
            SimpleNamespace(
                chars=[{}] * 100,
                images=[{"x0": 0, "x1": 100, "top": 0, "bottom": 100}],
                width=100,
                height=100,
            )
        ]
        with (
            patch(
                "shared_lib.services.curriculum_documents.parse_curriculum_pdf",
                return_value={
                    "assessments": [native],
                    "warnings": [],
                    "page_count": 1,
                },
            ),
            patch("pdfplumber.open", return_value=opened),
            patch(
                "shared_lib.services.curriculum_ocr.parse_scanned_curriculum",
                return_value={
                    "assessments": [scan],
                    "warnings": [],
                },
            ) as ocr,
        ):
            result = parse_document(b"%PDF-fixture", scan_layout="fa_legacy_v1")
        ocr.assert_called_once_with(
            b"%PDF-fixture", page_numbers=[1], layout_profile="fa_legacy_v1"
        )
        self.assertEqual(result["assessments"], [scan])


if __name__ == "__main__":
    unittest.main()

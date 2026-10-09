"""Run expensive PDF/OCR work in a killable, bounded, CPU-only child process."""

import asyncio
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from .curriculum_layout import LAYOUTS

PARSER_VERSION = "curriculum-text-1-numeric-1"
SUPPORTED_SCAN_LAYOUTS = frozenset(LAYOUTS)
MAX_RESULT_BYTES = 8 * 1024 * 1024


class CurriculumProcessingError(ValueError):
    """A stable non-sensitive failure code safe for administrator API responses."""


def validate_scan_layout(value: str | None) -> str | None:
    if value is not None and value not in SUPPORTED_SCAN_LAYOUTS:
        raise ValueError("Unsupported curriculum scan layout")
    return value


def current_parser_version(scan_layout: str | None = None) -> str:
    """Fingerprint parser/layout configuration and packaged weights without importing OCR runtimes."""
    validate_scan_layout(scan_layout)
    model = os.getenv("CURRICULUM_OCR_MODEL_VERSION", "tessdata-fast-system")
    digest = hashlib.sha256(json.dumps([PARSER_VERSION, model, scan_layout]).encode("utf-8"))
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "services/curriculum_ocr.py",
        "services/curriculum_numeric.py",
        "services/curriculum_layout.py",
        "services/curriculum_pipeline.py",
        "services/curriculum_control_cells.py",
        "data/curriculum_numeric.onnx",
        "data/curriculum_numeric.json",
    ):
        path = root / relative
        digest.update(relative.encode("utf-8"))
        # Missing assets still produce a cache key. Only scheduler-side model
        # construction loads ORT and validates the weight/metadata integrity.
        if path.is_file():
            with path.open("rb") as stream:
                digest.update(hashlib.file_digest(stream, "sha256").digest())
        else:
            digest.update(b"missing")
    return f"{PARSER_VERSION}-{digest.hexdigest()[:24]}"


def _setting(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(os.getenv(name, str(default)))))
    except ValueError:
        return default


def parse_timeout_seconds() -> int:
    return _setting("CURRICULUM_PARSE_TIMEOUT_SECONDS", 300, 30, 600)


def parse_memory_mb() -> int:
    return _setting("CURRICULUM_PARSE_MEMORY_MB", 1536, 512, 4096)


async def _terminate(process):
    # Tesseract inherits this process group: killing only Python leaves OCR alive.
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        killer = await asyncio.create_subprocess_exec(
            "taskkill",
            "/PID",
            str(process.pid),
            "/T",
            "/F",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await killer.wait()
        if process.returncode is None:
            process.kill()
    await process.wait()


async def parse_document_in_worker(content: bytes, *, scan_layout: str | None = None) -> dict:
    """Bound input/output, memory (Linux), CPU threads, wall time and process lifetime."""
    validate_scan_layout(scan_layout)
    with tempfile.TemporaryDirectory(prefix="mpb-curriculum-") as folder:
        source, target = Path(folder) / "source.pdf", Path(folder) / "result.json"
        source.write_bytes(content)
        environment = os.environ.copy()
        environment.update(
            {
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
                "OMP_THREAD_LIMIT": "1",
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "CUDA_VISIBLE_DEVICES": "",
                "CURRICULUM_PARSE_MEMORY_MB": str(parse_memory_mb()),
            }
        )
        arguments = [
            sys.executable,
            "-m",
            "shared_lib.services.curriculum_worker",
            str(source),
            str(target),
        ]
        if scan_layout is not None:
            arguments.extend(["--scan-layout", scan_layout])
        process = await asyncio.create_subprocess_exec(
            *arguments,
            env=environment,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            **(
                {"start_new_session": True}
                if os.name == "posix"
                else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            ),
        )
        try:
            await asyncio.wait_for(process.wait(), timeout=parse_timeout_seconds())
        except TimeoutError as exc:
            await _terminate(process)
            raise CurriculumProcessingError("parse_timeout") from exc
        except BaseException:
            await _terminate(process)
            raise
        if process.returncode or not target.is_file():
            raise CurriculumProcessingError("parse_failed")
        if target.stat().st_size > MAX_RESULT_BYTES:
            raise CurriculumProcessingError("result_limit")
        try:
            parsed = json.loads(target.read_text(encoding="utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise CurriculumProcessingError("parse_failed") from exc
        if not isinstance(parsed, dict):
            raise CurriculumProcessingError("parse_failed")
        return parsed

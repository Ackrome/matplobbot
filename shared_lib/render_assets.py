"""Allowed project inputs and safe inline raster detection shared by API/worker."""

import io
from pathlib import PurePosixPath

from PIL import Image

PROJECT_EXTENSIONS = frozenset(
    {
        ".tex",
        ".ltx",
        ".latex",
        ".sty",
        ".cls",
        ".bib",
        ".bst",
        ".md",
        ".txt",
        ".csv",
        ".mmd",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".pdf",
        ".eps",
        ".ps",
    }
)
MAX_ASSET_BYTES = 5 * 1024 * 1024
MAX_PROJECT_BYTES = 20 * 1024 * 1024
MAX_PROJECT_FILES = 100


def allowed_project_path(value: str) -> bool:
    """Accept relative non-hidden source/asset paths, never compiler config files."""
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and len(value) <= 255
        and all(ord(character) >= 32 for character in value)
        and all(
            part not in {"", ".", ".."} and not part.startswith(".") for part in value.split("/")
        )
        and path.suffix.lower() in PROJECT_EXTENSIONS
    )


def raster_content_type(content: bytes) -> str | None:
    """Identify and verify image bytes; extensions never determine inline MIME."""
    if len(content) > MAX_ASSET_BYTES:
        return None
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.width * image.height > 16_000_000:
                return None
            mime = {
                "PNG": "image/png",
                "JPEG": "image/jpeg",
                "GIF": "image/gif",
                "WEBP": "image/webp",
            }.get(image.format)
            image.verify()
            return mime
    except (OSError, ValueError, Image.DecompressionBombError):
        return None

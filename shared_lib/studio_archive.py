"""Read and write bounded Studio ZIP archives without extracting archive members."""

import io
import json
import stat
import struct
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import PurePosixPath

from shared_lib.render_assets import MAX_PROJECT_BYTES, MAX_PROJECT_FILES, allowed_project_path

MAX_ARCHIVE_BYTES = MAX_PROJECT_BYTES + 1024 * 1024
MAX_ENTRIES = MAX_PROJECT_FILES * 3
_COMMENT_PREFIX = b"Matplobbot-Studio-Project\n"
_FORMAT = 1
_MAIN_TYPES = {
    ".tex": "latex",
    ".ltx": "latex",
    ".latex": "latex",
    ".md": "markdown",
    ".mmd": "mermaid",
}
_TEXT_TYPES = frozenset(_MAIN_TYPES) | {".txt", ".csv", ".sty", ".cls", ".bib", ".bst"}
PROJECT_TYPES = ("latex", "markdown", "mermaid")


class ArchiveError(ValueError):
    """Only stable, user-facing codes cross the archive parsing boundary."""


@dataclass(frozen=True)
class ArchiveFile:
    path: str
    data: str | bytes


@dataclass(frozen=True)
class StudioArchive:
    files: tuple[ArchiveFile, ...]
    byte_count: int
    manifest: bool
    name: str | None
    project_type: str | None
    main: str | None

    def main_candidates(self):
        return [file.path for file in self.files if isinstance(file.data, str)]


def write_studio_zip(name, project_type, main, files) -> io.BytesIO:
    """Store metadata in the ZIP comment so ordinary ZIP member paths stay unchanged."""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        binary = []
        for item in files:
            archive.writestr(item.path, item.data)
            binary.append("1" if isinstance(item.data, bytes) else "0")
        manifest = {
            "version": _FORMAT,
            "name": name,
            "type": project_type,
            "main": main,
            "binary": "".join(binary),
        }
        comment = _COMMENT_PREFIX + json.dumps(
            manifest, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        if len(comment) <= zipfile.ZIP_MAX_COMMENT:
            archive.comment = comment
    output.seek(0)
    return output


def _check_index(data: bytes) -> None:
    # Bound Python's central directory allocation before constructing ZipInfo objects.
    offset = data.rfind(b"PK\x05\x06", max(0, len(data) - zipfile.ZIP_MAX_COMMENT - 22))
    if offset < 0 or len(data) - offset < 22:
        raise ArchiveError("archive_invalid")
    _, disk, start_disk, local_count, count, length, declared_start, comment_bytes = (
        struct.unpack_from("<4s4H2IH", data, offset)
    )
    if count > MAX_ENTRIES or length > 1024 * 1024:
        raise ArchiveError("archive_too_large")
    cursor = offset - length
    if (
        disk
        or start_disk
        or count != local_count
        or offset + 22 + comment_bytes != len(data)
        or declared_start > cursor
        or (offset >= 20 and data[offset - 20 : offset - 16] == b"PK\x06\x07")
    ):
        raise ArchiveError("archive_invalid")
    seen = 0
    while cursor < offset:
        if offset - cursor < 46 or data[cursor : cursor + 4] != b"PK\x01\x02":
            raise ArchiveError("archive_invalid")
        compressed, expanded = struct.unpack_from("<II", data, cursor + 20)
        name, extra, comment, entry_disk = struct.unpack_from("<HHHH", data, cursor + 28)
        local_offset = struct.unpack_from("<I", data, cursor + 42)[0]
        if entry_disk or 0xFFFFFFFF in (compressed, expanded, local_offset):
            raise ArchiveError("archive_invalid")
        cursor += 46 + name + extra + comment
        seen += 1
        if seen > MAX_ENTRIES:
            raise ArchiveError("archive_too_large")
    if cursor != offset or seen != count:
        raise ArchiveError("archive_invalid")


def _members(archive):
    members = {}
    directories = set()
    total = 0
    all_members = archive.infolist()
    if len(all_members) > MAX_ENTRIES:
        raise ArchiveError("archive_too_large")
    for info in all_members:
        name = info.filename
        file_type = stat.S_IFMT(info.external_attr >> 16) if info.create_system == 3 else 0
        if info.is_dir():
            if (
                not allowed_project_path(name + "source.tex")
                or info.file_size
                or info.orig_filename != name
                or file_type not in (0, stat.S_IFDIR)
            ):
                raise ArchiveError("archive_bad_files")
            directories.add(name[:-1])
            continue
        if (
            not allowed_project_path(name)
            or name in members
            or info.orig_filename != name
            or file_type not in (0, stat.S_IFREG)
            or info.flag_bits & 1
            or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
        ):
            raise ArchiveError("archive_bad_files")
        members[name] = info
        total += info.file_size
        if len(members) > MAX_PROJECT_FILES or total > MAX_PROJECT_BYTES:
            raise ArchiveError("archive_too_large")
    for name in members.keys() | directories:
        if any(str(parent) in members for parent in PurePosixPath(name).parents):
            raise ArchiveError("archive_bad_files")
    if directories.intersection(members) or not members:
        raise ArchiveError("archive_bad_files")
    return members, total


def _manifest(comment, count):
    if not comment.startswith(_COMMENT_PREFIX):
        return None
    try:
        item = json.loads(comment[len(_COMMENT_PREFIX) :])
        if (
            not isinstance(item, dict)
            or set(item) != {"version", "name", "type", "main", "binary"}
            or type(item["version"]) is not int
            or item["version"] != _FORMAT
            or not isinstance(item["name"], str)
            or not item["name"].strip()
            or len(item["name"]) > 160
            or "\x00" in item["name"]
            or item["type"] not in PROJECT_TYPES
            or (item["main"] is not None and not allowed_project_path(item["main"]))
            or not isinstance(item["binary"], str)
            or len(item["binary"]) != count
            or set(item["binary"]) - {"0", "1"}
        ):
            raise ArchiveError("archive_manifest_invalid")
        item["name"].encode("utf-8")
        return item
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ArchiveError("archive_manifest_invalid") from exc


def _read_member(archive, member, binary, strict):
    with archive.open(member) as stream:
        raw = stream.read(member.file_size + 1)
    if len(raw) != member.file_size:
        raise ArchiveError("archive_invalid")
    if binary:
        return raw
    try:
        text = raw.decode("utf-8")
        if "\x00" in text:
            raise UnicodeError("Invalid source text")
    except UnicodeError as exc:
        if strict:
            raise ArchiveError("archive_bad_files") from exc
        return raw
    return text


def read_studio_zip(data: bytes) -> StudioArchive:
    """Validate and read exact member bytes, with conservative legacy defaults."""
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ArchiveError("archive_too_large")
    _check_index(data)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members, total = _members(archive)
            manifest = _manifest(archive.comment, len(members))
            files = tuple(
                ArchiveFile(
                    path,
                    _read_member(
                        archive,
                        member,
                        manifest["binary"][index] == "1"
                        if manifest
                        else PurePosixPath(path).suffix.lower() not in _TEXT_TYPES,
                        manifest is not None,
                    ),
                )
                for index, (path, member) in enumerate(members.items())
            )
    except (zipfile.BadZipFile, OSError, ValueError, RuntimeError, EOFError, zlib.error) as exc:
        if isinstance(exc, ArchiveError):
            raise
        raise ArchiveError("archive_invalid") from exc
    text_paths = {file.path for file in files if isinstance(file.data, str)}
    if not text_paths:
        raise ArchiveError("archive_no_main")
    if manifest:
        main = manifest["main"]
        if main is not None and main not in text_paths:
            raise ArchiveError("archive_manifest_invalid")
        return StudioArchive(files, total, True, manifest["name"], manifest["type"], main)
    conventional = text_paths.intersection({"main.tex", "main.md", "main.mmd"})
    plausible = conventional or {
        path for path in text_paths if PurePosixPath(path).suffix.lower() in _MAIN_TYPES
    }
    main = next(iter(plausible)) if len(plausible) == 1 else None
    project_type = _MAIN_TYPES[PurePosixPath(main).suffix.lower()] if main else None
    return StudioArchive(files, total, False, None, project_type, main)

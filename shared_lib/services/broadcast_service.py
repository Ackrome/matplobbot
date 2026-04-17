import asyncio
import re
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MAX_TELEGRAM_MESSAGES_PER_SECOND = 30.0
DEFAULT_BROADCAST_RATE_PER_SECOND = 25.0
DEFAULT_BROADCAST_ACTIVE_DAYS = 180
TELEGRAM_MESSAGE_SAFE_CHARS = 3900
DEFAULT_BROADCAST_TITLE = "Matplobbot update"

REPO_ROOT = Path(__file__).resolve().parents[2]
ANNOUNCEMENT_CANDIDATES = (
    Path("docs/announcement.md"),
    Path("docs/ANNOUNCEMENT.md"),
)
CHANGELOG_CANDIDATES = (
    Path("docs/changelog-from-0.7.1.md"),
    Path("docs/CHANGELOG.md"),
)

SendMessageCallable = Callable[[int, str], Awaitable[Any]]


@dataclass(slots=True)
class BroadcastFailure:
    user_id: int
    chunk_index: int
    error_type: str
    error: str


@dataclass(slots=True)
class BroadcastResult:
    target_users: int
    total_messages: int
    sent_messages: int = 0
    failed_messages: int = 0
    skipped_messages: int = 0
    dry_run: bool = True
    rate_per_second: float = DEFAULT_BROADCAST_RATE_PER_SECOND
    failures: list[BroadcastFailure] = field(default_factory=list)

    @property
    def failed_users(self) -> int:
        return len({failure.user_id for failure in self.failures})


def normalize_broadcast_rate(rate_per_second: float | int | str | None) -> float:
    try:
        parsed = float(rate_per_second) if rate_per_second is not None else None
    except (TypeError, ValueError):
        parsed = None

    if parsed is None or parsed <= 0:
        parsed = DEFAULT_BROADCAST_RATE_PER_SECOND

    return min(MAX_TELEGRAM_MESSAGES_PER_SECOND, max(1.0, parsed))


def resolve_default_broadcast_files(root: Path = REPO_ROOT) -> list[Path]:
    files: list[Path] = []
    seen_paths: set[str] = set()

    for candidate in ANNOUNCEMENT_CANDIDATES:
        path = root / candidate
        path_key = str(path.resolve()).casefold()
        if path.exists() and path_key not in seen_paths:
            seen_paths.add(path_key)
            files.append(path)

    for candidate in CHANGELOG_CANDIDATES:
        path = root / candidate
        path_key = str(path.resolve()).casefold()
        if path.exists() and path_key not in seen_paths:
            seen_paths.add(path_key)
            files.append(path)
            break

    return files


def resolve_broadcast_files(paths: Sequence[str | Path] | None, root: Path = REPO_ROOT) -> list[Path]:
    if not paths:
        files = resolve_default_broadcast_files(root)
    else:
        files = []
        for raw_path in paths:
            path = Path(raw_path)
            files.append(path if path.is_absolute() else root / path)

    missing = [str(path) for path in files if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Broadcast source file not found: {', '.join(missing)}")

    if not files:
        raise FileNotFoundError(
            "No broadcast source files found. Add docs/announcement.md or pass --file."
        )

    return files


def _markdown_to_plain_text(markdown: str) -> str:
    text = re.sub(r"!\[[^\]]*]\([^)]+\)", "", markdown)
    text = re.sub(r"\[([^\]]+)]\(([^)]+)\)", r"\1 (\2)", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_broadcast_text(
    paths: Sequence[str | Path] | None = None,
    *,
    root: Path = REPO_ROOT,
    title: str = DEFAULT_BROADCAST_TITLE,
) -> tuple[str, list[Path]]:
    files = resolve_broadcast_files(paths, root=root)
    sections = [title.strip()]

    for path in files:
        body = _markdown_to_plain_text(path.read_text(encoding="utf-8"))
        if body:
            display_name = path.relative_to(root) if path.is_relative_to(root) else path.name
            sections.append(f"{display_name}\n\n{body}")

    return "\n\n".join(section for section in sections if section), files


def _split_oversized_block(block: str, max_chars: int) -> list[str]:
    if len(block) <= max_chars:
        return [block]

    chunks: list[str] = []
    current = ""

    for line in block.splitlines():
        candidate = f"{current}\n{line}".strip() if current else line
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        while len(line) > max_chars:
            chunks.append(line[:max_chars].rstrip())
            line = line[max_chars:].lstrip()
        current = line

    if current:
        chunks.append(current)

    return chunks


def split_telegram_message(
    text: str,
    *,
    max_chars: int = TELEGRAM_MESSAGE_SAFE_CHARS,
) -> list[str]:
    normalized_text = text.strip()
    if not normalized_text:
        return []

    body_limit = max(1000, max_chars - 32)
    raw_chunks: list[str] = []
    current = ""

    for block in re.split(r"\n{2,}", normalized_text):
        block = block.strip()
        if not block:
            continue

        for piece in _split_oversized_block(block, body_limit):
            candidate = f"{current}\n\n{piece}".strip() if current else piece
            if len(candidate) <= body_limit:
                current = candidate
            else:
                if current:
                    raw_chunks.append(current)
                current = piece

    if current:
        raw_chunks.append(current)

    if len(raw_chunks) <= 1:
        return raw_chunks

    total = len(raw_chunks)
    return [f"[{index}/{total}]\n{chunk}" for index, chunk in enumerate(raw_chunks, start=1)]


def dedupe_user_ids(user_ids: Iterable[int]) -> list[int]:
    unique: list[int] = []
    seen: set[int] = set()
    for raw_user_id in user_ids:
        user_id = int(raw_user_id)
        if user_id in seen:
            continue
        seen.add(user_id)
        unique.append(user_id)
    return unique


def _format_source_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


async def broadcast_chunks_to_users(
    user_ids: Sequence[int],
    chunks: Sequence[str],
    send_message: SendMessageCallable,
    *,
    rate_per_second: float | int | str | None = DEFAULT_BROADCAST_RATE_PER_SECOND,
    dry_run: bool = True,
) -> BroadcastResult:
    target_user_ids = dedupe_user_ids(user_ids)
    message_chunks = [chunk for chunk in chunks if chunk]
    effective_rate = normalize_broadcast_rate(rate_per_second)
    result = BroadcastResult(
        target_users=len(target_user_ids),
        total_messages=len(target_user_ids) * len(message_chunks),
        dry_run=dry_run,
        rate_per_second=effective_rate,
    )

    if dry_run or not target_user_ids or not message_chunks:
        return result

    delay_seconds = 1.0 / effective_rate

    for user_id in target_user_ids:
        for chunk_index, chunk in enumerate(message_chunks, start=1):
            try:
                await send_message(user_id, chunk)
                result.sent_messages += 1
            except Exception as exc:
                result.failed_messages += 1
                result.skipped_messages += len(message_chunks) - chunk_index
                result.failures.append(
                    BroadcastFailure(
                        user_id=user_id,
                        chunk_index=chunk_index,
                        error_type=type(exc).__name__,
                        error=str(exc),
                    )
                )
                break

            await asyncio.sleep(delay_seconds)

    return result


def format_broadcast_plan(
    *,
    user_count: int,
    chunks: Sequence[str],
    files: Sequence[Path],
    active_days: int,
    rate_per_second: float | int | str | None,
    dry_run: bool,
    include_schedule_subscribers: bool = True,
) -> str:
    mode = "dry run" if dry_run else "execute"
    effective_rate = normalize_broadcast_rate(rate_per_second)
    source_list = ", ".join(_format_source_path(path) for path in files)
    total_messages = user_count * len(chunks)
    active_scope = f"{active_days} days"
    if include_schedule_subscribers:
        active_scope += " + active schedule subscriptions"
    return (
        f"Broadcast plan ({mode})\n"
        f"Users: {user_count}\n"
        f"Chunks per user: {len(chunks)}\n"
        f"Telegram messages: {total_messages}\n"
        f"Rate limit: {effective_rate:g} msg/sec (cap {MAX_TELEGRAM_MESSAGES_PER_SECOND:g})\n"
        f"Active window: {active_scope}\n"
        f"Sources: {source_list}"
    )


def format_broadcast_result(result: BroadcastResult) -> str:
    lines = [
        "Broadcast result",
        f"Users: {result.target_users}",
        f"Messages planned: {result.total_messages}",
        f"Sent: {result.sent_messages}",
        f"Failed messages: {result.failed_messages}",
        f"Failed users: {result.failed_users}",
        f"Skipped after failures: {result.skipped_messages}",
        f"Rate limit: {result.rate_per_second:g} msg/sec",
    ]

    if result.failures:
        sample = result.failures[:5]
        lines.append("First failures:")
        lines.extend(
            f"- {failure.user_id} chunk {failure.chunk_index}: "
            f"{failure.error_type}: {failure.error}"
            for failure in sample
        )

    return "\n".join(lines)

import re

HTML_TAG_RE = re.compile(r"(</?([a-zA-Z0-9_-]+)(?:\s+[^>]*)?>)")


def split_telegram_html_message(text: str, max_chars: int = 3800) -> list[str]:
    """
    Safely split an HTML-formatted message into valid HTML chunks under max_chars.
    Guarantees that:
    1. HTML tags are never split in half.
    2. Tags left open at the end of a chunk are safely closed.
    3. The same open tags are reopened at the beginning of the next chunk.
    """
    if not isinstance(max_chars, int) or max_chars < 1:
        raise ValueError("max_chars must be a positive integer")

    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    tokens: list[tuple[str, str, bool, bool, str]] = []
    last_end = 0
    for match in HTML_TAG_RE.finditer(text):
        start, end = match.span()
        if start > last_end:
            tokens.append(("text", text[last_end:start], False, False, ""))
        full_tag = match.group(1)
        tag_name = match.group(2).lower()
        is_closing = full_tag.startswith("</")
        is_self_closing = full_tag.endswith("/>")
        tokens.append(("tag", full_tag, is_closing, is_self_closing, tag_name))
        last_end = end
    if last_end < len(text):
        tokens.append(("text", text[last_end:], False, False, ""))

    chunks: list[str] = []
    current_tokens: list[str] = []
    current_len = 0
    open_tags: list[tuple[str, str]] = []

    def get_closing_tags() -> str:
        return "".join(f"</{tag_name}>" for tag_name, _ in reversed(open_tags))

    def get_opening_tags() -> str:
        return "".join(full_tag for _, full_tag in open_tags)

    def flush_chunk():
        nonlocal current_tokens, current_len
        if not current_tokens:
            return
        closing = get_closing_tags()
        if closing:
            current_tokens.append(closing)
        chunk_str = "".join(current_tokens).strip()
        if chunk_str:
            chunks.append(chunk_str)
        reopened = get_opening_tags()
        current_tokens = [reopened] if reopened else []
        current_len = len(reopened)

    for kind, content, is_closing, is_self_closing, tag_name in tokens:
        if kind == "tag":
            overhead = len(get_closing_tags())
            if current_len + len(content) + overhead > max_chars and current_tokens:
                flush_chunk()

            current_tokens.append(content)
            current_len += len(content)

            if not is_self_closing:
                if is_closing:
                    for idx in range(len(open_tags) - 1, -1, -1):
                        if open_tags[idx][0] == tag_name:
                            open_tags.pop(idx)
                            break
                else:
                    open_tags.append((tag_name, content))
        else:
            remaining = content
            while remaining:
                overhead = len(get_closing_tags())
                available = max_chars - current_len - overhead
                if len(remaining) <= available:
                    current_tokens.append(remaining)
                    current_len += len(remaining)
                    break
                else:
                    if available <= 0:
                        if len(get_opening_tags()) + len(get_closing_tags()) >= max_chars:
                            raise ValueError(
                                "max_chars is too small to preserve the open HTML tags"
                            )
                        flush_chunk()
                        continue

                    slice_candidate = remaining[:available]
                    split_idx = -1
                    for delim in ["\n\n", "\n", " "]:
                        pos = slice_candidate.rfind(delim)
                        if pos > 0:
                            split_idx = pos + len(delim)
                            break
                    if split_idx <= 0:
                        split_idx = available

                    piece = remaining[:split_idx]
                    remaining = remaining[split_idx:]
                    current_tokens.append(piece)
                    flush_chunk()

    if current_tokens:
        closing = get_closing_tags()
        if closing:
            current_tokens.append(closing)
        chunk_str = "".join(current_tokens).strip()
        if chunk_str:
            chunks.append(chunk_str)

    return chunks

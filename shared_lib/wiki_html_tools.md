# `html_tools.py`

## Purpose

Provides safe splitting of Telegram HTML messages without breaking tags.

## Public API

- `split_telegram_html_message(text, max_chars=3800)` returns a list of balanced HTML chunks. Open tags are closed at a chunk boundary and reopened in the next chunk.

## Usage

```python
from shared_lib.html_tools import split_telegram_html_message

chunks = split_telegram_html_message("<b>" + long_text + "</b>")
```

`max_chars` must be positive and large enough to contain the tags that need to remain open.

## Dependencies and side effects

Uses only Python's `re` module. It does not perform I/O or mutate the input string.

## Maintenance notes

Keep the tokenizer aligned with Telegram-supported HTML tags. Preserve the guard against impossible limits so malformed caller settings cannot cause an infinite loop.

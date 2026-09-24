import asyncio
import base64
import datetime
import html
import io
import logging
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

from shared_lib.celery_app import dispatch_traced_task

# Импортируем задачи из shared_lib
from shared_lib.tasks import render_html_task, render_latex, render_mermaid, render_pdf_task

logger = logging.getLogger(__name__)


_TELEGRAM_SIMPLE_TAGS = {
    "b": "b",
    "strong": "b",
    "i": "i",
    "em": "i",
    "u": "u",
    "ins": "u",
    "s": "s",
    "strike": "s",
    "del": "s",
    "code": "code",
    "pre": "pre",
    "tg-spoiler": "tg-spoiler",
}
_SAFE_LINK_SCHEMES = {"http", "https", "tg", "mailto"}
_LANGUAGE_CLASS_PATTERN = re.compile(r"^language-[A-Za-z0-9_+.-]+$")


class _TelegramHTMLParser(HTMLParser):
    """Render arbitrary HTML into Telegram's supported, escaped HTML subset."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.open_tags: list[tuple[str, str]] = []
        self.list_stack: list[dict[str, int | str]] = []

    @staticmethod
    def _attrs(attributes: list[tuple[str, str | None]]) -> dict[str, str]:
        return {name.lower(): value or "" for name, value in attributes}

    def _push(self, source_tag: str, closing_text: str = "") -> None:
        self.open_tags.append((source_tag, closing_text))

    def _close_until(self, source_tag: str) -> None:
        matching_index = next(
            (
                index
                for index in range(len(self.open_tags) - 1, -1, -1)
                if self.open_tags[index][0] == source_tag
            ),
            None,
        )
        if matching_index is None:
            return
        while len(self.open_tags) > matching_index:
            _, closing_text = self.open_tags.pop()
            self.parts.append(closing_text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attributes = self._attrs(attrs)

        if tag in {"br"}:
            self.parts.append("\n")
            return
        if tag == "hr":
            self.parts.append("\n———\n")
            return
        if tag == "img":
            alt_text = attributes.get("alt", "").strip()
            if alt_text:
                self.parts.append(html.escape(alt_text))
            return
        if tag in {"ul", "ol"}:
            self.list_stack.append({"tag": tag, "counter": 0})
            self._push(tag, "")
            return
        if tag == "li":
            depth = max(len(self.list_stack) - 1, 0)
            prefix = "• "
            if self.list_stack and self.list_stack[-1]["tag"] == "ol":
                self.list_stack[-1]["counter"] = int(self.list_stack[-1]["counter"]) + 1
                prefix = f"{self.list_stack[-1]['counter']}. "
            self.parts.append(f"{'  ' * depth}{prefix}")
            self._push(tag, "\n")
            return
        if tag in {"p", "div", "section", "article"}:
            self._push(tag, "\n")
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("<b>")
            self._push(tag, "</b>\n")
            return
        if tag in {"table", "thead", "tbody", "tfoot"}:
            self._push(tag, "")
            return
        if tag == "tr":
            self._push(tag, "\n")
            return
        if tag == "th":
            self.parts.append("<b>")
            self._push(tag, "</b> | ")
            return
        if tag == "td":
            self._push(tag, " | ")
            return
        if tag == "blockquote":
            expandable = " expandable" if "expandable" in attributes else ""
            self.parts.append(f"<blockquote{expandable}>")
            self._push(tag, "</blockquote>\n")
            return
        if tag == "a":
            href = attributes.get("href", "").strip()
            parsed_href = urlparse(href)
            scheme = parsed_href.scheme.lower()
            has_safe_target = (scheme in {"http", "https"} and bool(parsed_href.netloc)) or (
                scheme in {"mailto", "tg"} and bool(parsed_href.path or parsed_href.netloc)
            )
            if scheme in _SAFE_LINK_SCHEMES and has_safe_target:
                self.parts.append(f'<a href="{html.escape(href, quote=True)}">')
                self._push(tag, "</a>")
            else:
                self._push(tag, "")
            return
        if tag == "span" and "tg-spoiler" in attributes.get("class", "").split():
            self.parts.append("<tg-spoiler>")
            self._push(tag, "</tg-spoiler>")
            return
        if tag in _TELEGRAM_SIMPLE_TAGS:
            output_tag = _TELEGRAM_SIMPLE_TAGS[tag]
            rendered_attributes = ""
            if output_tag == "code":
                language_class = attributes.get("class", "").strip()
                inside_pre = any(source_tag == "pre" for source_tag, _closing in self.open_tags)
                if inside_pre and _LANGUAGE_CLASS_PATTERN.fullmatch(language_class):
                    rendered_attributes = f' class="{language_class}"'
            self.parts.append(f"<{output_tag}{rendered_attributes}>")
            self._push(tag, f"</{output_tag}>")
            return

        # Unknown tags are discarded while their text is retained and escaped.
        self._push(tag, "")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        self._close_until(tag)
        if tag in {"ul", "ol"} and self.list_stack:
            self.list_stack.pop()

    def handle_data(self, data: str) -> None:
        self.parts.append(html.escape(data, quote=False))

    def result(self) -> str:
        while self.open_tags:
            _, closing_text = self.open_tags.pop()
            self.parts.append(closing_text)
        rendered = "".join(self.parts)
        rendered = re.sub(r"[ \t]+\n", "\n", rendered)
        rendered = re.sub(r"\n{3,}", "\n\n", rendered)
        return rendered.strip()


def convert_html_to_telegram_html(html_content: str) -> str:
    """Convert HTML to Telegram's allowlisted HTML subset without leaking raw tags."""
    parser = _TelegramHTMLParser()
    parser.feed(html_content)
    parser.close()
    return parser.result()


# --- Асинхронные обертки для Celery задач ---


async def render_latex_to_image(
    latex_string: str, padding: int, dpi: int = 300, is_display_override: bool | None = None
) -> io.BytesIO:
    """
    Отправляет задачу рендеринга LaTeX в Celery.
    """
    is_display = is_display_override if is_display_override is not None else True

    # Отправляем задачу (.delay не блокирует, возвращает AsyncResult)
    task = dispatch_traced_task(render_latex, latex_string, padding, dpi, is_display)

    # Блокирующее ожидание переносим в тред
    def wait_for_result():
        return task.get(timeout=40)

    try:
        result = await asyncio.to_thread(wait_for_result)
        if result["status"] == "success":
            return io.BytesIO(base64.b64decode(result["image"]))
        else:
            raise ValueError(f"LaTeX Worker Error: {result.get('error')}")
    except Exception as e:
        logger.error(f"LaTeX render failed: {e}")
        raise ValueError(f"Ошибка рендеринга LaTeX: {e}") from e


async def render_mermaid_to_image(mermaid_code: str) -> io.BytesIO:
    """
    Отправляет задачу рендеринга Mermaid в Celery.
    """
    task = dispatch_traced_task(render_mermaid, mermaid_code)

    def wait_for_result():
        return task.get(timeout=40)

    try:
        result = await asyncio.to_thread(wait_for_result)
        if result["status"] == "success":
            return io.BytesIO(base64.b64decode(result["image"]))
        else:
            raise ValueError(f"Mermaid Worker Error: {result.get('error')}")
    except Exception as e:
        logger.error(f"Mermaid render failed: {e}")
        raise ValueError(f"Ошибка рендеринга Mermaid: {e}") from e


async def convert_md_to_pdf_pandoc(
    markdown_string: str,
    title: str,
    contributors: list | None = None,
    last_modified_date: str | None = None,
) -> io.BytesIO:
    """
    Отправляет задачу конвертации Markdown -> PDF в Celery (Pandoc).
    """
    # Подготовка данных (сериализуемых в JSON) для передачи воркеру
    if contributors:
        author_links = [
            r"\href{" + f"{c['html_url']}" + r"}{" + f"{c['login']}" + r"}" for c in contributors
        ]
        author_string = ", ".join(author_links)
    else:
        author_string = "Matplobbot"

    date_string = last_modified_date or datetime.datetime.now().strftime("%d %B %Y")

    # Отправка задачи
    task = dispatch_traced_task(
        render_pdf_task,
        markdown_string,
        title,
        author_string,
        date_string,
    )

    def wait_for_result():
        # PDF может собираться долго, ставим таймаут побольше
        return task.get(timeout=120)

    try:
        result = await asyncio.to_thread(wait_for_result)
        if result["status"] == "success":
            return io.BytesIO(base64.b64decode(result["pdf"]))
        else:
            raise ValueError(f"PDF Worker Error: {result.get('error')}")
    except Exception as e:
        logger.error(f"PDF render failed: {e}")
        # Усекаем сообщение об ошибке, чтобы не спамить пользователю огромными логами
        err_msg = str(e)
        if len(err_msg) > 200:
            err_msg = err_msg[:200] + "..."
        raise ValueError(f"Ошибка создания PDF: {err_msg}") from e


async def _prepare_html_with_katex(content: str, page_title: str) -> str:
    """
    Отправляет задачу генерации HTML (Markdown -> HTML + KaTeX) в Celery.
    """
    task = dispatch_traced_task(render_html_task, content, page_title)

    def wait_for_result():
        return task.get(timeout=60)

    try:
        result = await asyncio.to_thread(wait_for_result)
        if result["status"] == "success":
            return result["html"]
        else:
            raise ValueError(f"HTML Worker Error: {result.get('error')}")
    except Exception as e:
        logger.error(f"HTML render failed: {e}")
        raise ValueError(f"Ошибка создания HTML: {e}") from e

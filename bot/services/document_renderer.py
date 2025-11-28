import io
import asyncio
import base64
import logging
import datetime
import re

# Импортируем задачи из shared_lib
from shared_lib.tasks import render_latex, render_mermaid, render_pdf_task, render_html_task

logger = logging.getLogger(__name__)

def convert_html_to_telegram_html(html_content: str) -> str:
    """
    Конвертирует сложный HTML в упрощенный, поддерживаемый Telegram.
    Эта функция работает с текстом, поэтому выполняется локально (быстро).
    """
    # Pre-formatted text (code blocks)
    html_content = html_content.replace('<pre><code>', '<pre>').replace('</code></pre>', '</pre>')

    # Headers to bold
    for i in range(1, 7):
        html_content = html_content.replace(f'<h{i}>', '<b>').replace(f'</h{i}>', '</b>\n')

    # Paragraphs to newlines
    html_content = html_content.replace('<p>', '').replace('</p>', '\n')

    # Lists
    html_content = html_content.replace('<ul>', '').replace('</ul>', '')
    html_content = html_content.replace('<ol>', '').replace('</ol>', '')
    html_content = html_content.replace('<li>', '• ').replace('</li>', '\n')

    # Bold and Italic
    html_content = html_content.replace('<em>', '<i>').replace('</em>', '</i>')
    html_content = html_content.replace('<strong>', '<b>').replace('</strong>', '</b>')
    
    # Horizontal rule
    html_content = html_content.replace('<hr>', '---').replace('<hr />', '---')

    # Blockquotes
    html_content = html_content.replace('<blockquote>', '').replace('</blockquote>', '\n')

    # Basic table conversion
    html_content = html_content.replace('<table>', '').replace('</table>', '')
    html_content = html_content.replace('<thead>', '').replace('</thead>', '')
    html_content = html_content.replace('<tbody>', '').replace('</tbody>', '')
    html_content = html_content.replace('<tr>', '').replace('</tr>', '\n')
    html_content = html_content.replace('<th>', '<b>').replace('</th>', '</b> | ')
    html_content = html_content.replace('<td>', '').replace('</td>', ' | ')

    # Clean up extra newlines and spaces
    lines = [line.strip() for line in html_content.split('\n')]
    return '\n'.join(filter(None, lines))


# --- Асинхронные обертки для Celery задач ---

async def render_latex_to_image(latex_string: str, padding: int, dpi: int = 300, is_display_override: bool | None = None) -> io.BytesIO:
    """
    Отправляет задачу рендеринга LaTeX в Celery.
    """
    is_display = is_display_override if is_display_override is not None else True
    
    # Отправляем задачу (.delay не блокирует, возвращает AsyncResult)
    task = render_latex.delay(latex_string, padding, dpi, is_display)
    
    # Блокирующее ожидание переносим в тред
    def wait_for_result():
        return task.get(timeout=40)

    try:
        result = await asyncio.to_thread(wait_for_result)
        if result['status'] == 'success':
            return io.BytesIO(base64.b64decode(result['image']))
        else:
            raise ValueError(f"LaTeX Worker Error: {result.get('error')}")
    except Exception as e:
        logger.error(f"LaTeX render failed: {e}")
        raise ValueError(f"Ошибка рендеринга LaTeX: {e}")


async def render_mermaid_to_image(mermaid_code: str) -> io.BytesIO:
    """
    Отправляет задачу рендеринга Mermaid в Celery.
    """
    task = render_mermaid.delay(mermaid_code)
    
    def wait_for_result():
        return task.get(timeout=40)

    try:
        result = await asyncio.to_thread(wait_for_result)
        if result['status'] == 'success':
            return io.BytesIO(base64.b64decode(result['image']))
        else:
            raise ValueError(f"Mermaid Worker Error: {result.get('error')}")
    except Exception as e:
        logger.error(f"Mermaid render failed: {e}")
        raise ValueError(f"Ошибка рендеринга Mermaid: {e}")


async def convert_md_to_pdf_pandoc(markdown_string: str, title: str, contributors: list | None = None, last_modified_date: str | None = None) -> io.BytesIO:
    """
    Отправляет задачу конвертации Markdown -> PDF в Celery (Pandoc).
    """
    # Подготовка данных (сериализуемых в JSON) для передачи воркеру
    if contributors:
        author_links = [r"\href{" + f"{c['html_url']}" + r"}{" + f"{c['login']}" + r"}" for c in contributors]
        author_string = ", ".join(author_links)
    else:
        author_string = "Matplobbot"

    date_string = last_modified_date or datetime.datetime.now().strftime("%d %B %Y")

    # Отправка задачи
    task = render_pdf_task.delay(markdown_string, title, author_string, date_string)

    def wait_for_result():
        # PDF может собираться долго, ставим таймаут побольше
        return task.get(timeout=120)

    try:
        result = await asyncio.to_thread(wait_for_result)
        if result['status'] == 'success':
            return io.BytesIO(base64.b64decode(result['pdf']))
        else:
            raise ValueError(f"PDF Worker Error: {result.get('error')}")
    except Exception as e:
        logger.error(f"PDF render failed: {e}")
        # Усекаем сообщение об ошибке, чтобы не спамить пользователю огромными логами
        err_msg = str(e)
        if len(err_msg) > 200: err_msg = err_msg[:200] + "..."
        raise ValueError(f"Ошибка создания PDF: {err_msg}")


async def _prepare_html_with_katex(content: str, page_title: str) -> str:
    """
    Отправляет задачу генерации HTML (Markdown -> HTML + KaTeX) в Celery.
    """
    task = render_html_task.delay(content, page_title)

    def wait_for_result():
        return task.get(timeout=60)

    try:
        result = await asyncio.to_thread(wait_for_result)
        if result['status'] == 'success':
            return result['html']
        else:
            raise ValueError(f"HTML Worker Error: {result.get('error')}")
    except Exception as e:
        logger.error(f"HTML render failed: {e}")
        raise ValueError(f"Ошибка создания HTML: {e}")
import io
import re
import os
import asyncio
import base64
import logging
import html
import datetime
import tempfile
import subprocess
from bs4 import BeautifulSoup
from markdown_it import MarkdownIt

# Импортируем конфигурацию (пути к шаблонам Pandoc и фильтрам остались нужны для PDF)
from ..config import *

# Импортируем задачи Celery
from shared_lib.tasks import render_latex, render_mermaid

logger = logging.getLogger(__name__)

def _pmatrix_hline_fixer(match: re.Match) -> str:
    """
    Callback-функция для исправления \\hline внутри pmatrix.
    Используется при подготовке Markdown для PDF конвертации.
    """
    matrix_content = match.group(1)
    if r'\hline' in matrix_content:
        lines = matrix_content.strip().split(r'\\')
        num_cols = 0
        for line in lines:
            if r'\hline' in line.strip(): continue
            clean_line = re.sub(r'\\text\{.*?\}', '', line)
            current_cols = clean_line.count('&') + 1
            if current_cols > num_cols:
                num_cols = current_cols
        if num_cols == 0 and len(lines) > 0: num_cols = 1
        if num_cols > 0:
            col_spec = 'c' * num_cols
            return f'\\left(\\begin{{array}}{{{col_spec}}}{matrix_content}\\end{{array}}\\right)'
    return match.group(0)


def convert_html_to_telegram_html(html_content: str) -> str:
    """Converts generic HTML to Telegram-supported HTML."""
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

    # Blockquotes are not directly supported, just remove tags
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


# --- LaTeX Rendering (Via Celery) ---

async def render_latex_to_image(latex_string: str, padding: int, dpi: int = 300, is_display_override: bool | None = None) -> io.BytesIO:
    """
    Асинхронная функция, которая отправляет задачу рендеринга LaTeX в очередь Celery.
    """
    is_display = is_display_override if is_display_override is not None else True

    # Отправляем задачу в Redis. .delay() возвращает AsyncResult.
    task = render_latex.delay(latex_string, padding, dpi, is_display)

    # Функция для блокирующего ожидания результата (будет запущена в отдельном потоке)
    def wait_for_task():
        # Ждем результат максимум 40 секунд (чуть меньше лимита воркера)
        return task.get(timeout=40)

    try:
        # Используем to_thread, чтобы ожидание ответа от Redis не блокировало Event Loop бота
        result = await asyncio.to_thread(wait_for_task)

        if result.get('status') == 'success':
            # Декодируем Base64 обратно в байты изображения
            img_data = base64.b64decode(result['image'])
            return io.BytesIO(img_data)
        else:
            error_msg = result.get('error', 'Unknown error')
            raise ValueError(f"Ошибка рендеринга LaTeX (Worker): {error_msg}")

    except Exception as e:
        logger.error(f"Failed to render LaTeX via Celery: {e}", exc_info=True)
        # Если Celery недоступен или таймаут, пробрасываем ошибку пользователю
        raise ValueError(f"Сервис рендеринга временно недоступен или произошла ошибка: {e}")


# --- Mermaid Rendering (Via Celery) ---

async def render_mermaid_to_image(mermaid_code: str) -> io.BytesIO:
    """
    Асинхронная функция, которая отправляет задачу рендеринга Mermaid в очередь Celery.
    """
    task = render_mermaid.delay(mermaid_code)

    def wait_for_task():
        return task.get(timeout=40)

    try:
        result = await asyncio.to_thread(wait_for_task)

        if result.get('status') == 'success':
            img_data = base64.b64decode(result['image'])
            return io.BytesIO(img_data)
        else:
            error_msg = result.get('error', 'Unknown error')
            raise ValueError(f"Ошибка рендеринга Mermaid (Worker): {error_msg}")

    except Exception as e:
        logger.error(f"Failed to render Mermaid via Celery: {e}", exc_info=True)
        raise ValueError(f"Сервис рендеринга временно недоступен: {e}")


# --- Markdown to PDF (Local Pandoc) ---
# Эту логику пока оставляем локальной, так как она требует передачи контекста (заголовки, файлы)
# и сложнее для сериализации. В будущем тоже стоит вынести в таску.

def _convert_md_to_pdf_pandoc_sync(markdown_string: str, title: str, contributors: list | None = None, last_modified_date: str | None = None) -> io.BytesIO:
    """
    Финальная, надежная функция для конвертации Markdown в PDF.
    Стратегия "Многоуровневой защиты":
    1. Предобработка Markdown для исправления частых ошибок пользователя.
    2. Генерация .tex файла с помощью Pandoc.
    3. Постобработка .tex файла для исправления артефактов Pandoc.
    4. Компиляция в PDF.
    """
    # --- ЭТАП 1: Предобработка Markdown для исправления ошибок пользователя ---

    # 1. Перемещение \tag{...} внутрь окружений.
    markdown_string = re.sub(
        r'(\\end\{([a-zA-Z\*]+)\})(\s*\\tag\{.*?\})',
        r'\3 \1',
        markdown_string,
        flags=re.DOTALL
    )

    # 2. НОВОЕ ИСПРАВЛЕНИЕ: Обработка устаревшей команды \atop после окружения.
    # Мы заменяем ее на новую строку (\\) и перемещаем текст внутрь окружения.
    markdown_string = re.sub(
        r'(\\end\{([a-zA-Z\*]+)\})(\s*\\atop\s*(\\text\{.*?\}))',
        r'\\ \4 \1', # --> \\ \text{...} \end{align}
        markdown_string,
        flags=re.DOTALL
    )

    # 3. Конвертация align* в align, если внутри используется \tag.
    def fix_starred_env_with_tag(match):
        env_name = match.group(1)
        content = match.group(2)
        if r'\tag' in content:
            return f"\\begin{{{env_name}}}{content}\\end{{{env_name}}}"
        return match.group(0)

    markdown_string = re.sub(
        r'\\begin\{([a-zA-Z]+)\*\}(.*?)\\end\{\1\*\}',
        fix_starred_env_with_tag,
        markdown_string,
        flags=re.DOTALL
    )

    # 4. Исправление \hline внутри pmatrix.
    markdown_string = re.sub(
        r'\\begin{pmatrix}(.*?)\\end{pmatrix}',
        _pmatrix_hline_fixer,
        markdown_string,
        flags=re.DOTALL
    )

    if contributors:
        author_links = [r"\href{" + f"{c['html_url']}" + r"}{" + f"{c['login']}" + r"}" for c in contributors]
        author_string = ", ".join(author_links)
    else:
        author_string = "Matplobbot"

    date_string = last_modified_date or datetime.datetime.now().strftime("%d %B %Y")

    with tempfile.TemporaryDirectory() as temp_dir:
        header_path = os.path.join(temp_dir, 'header.tex')
        with open(header_path, 'w', encoding='utf-8') as f:
            f.write(PANDOC_HEADER_INCLUDES)

        try:
            base_name = 'document'
            tex_path = os.path.join(temp_dir, f'{base_name}.tex')
            pdf_path = os.path.join(temp_dir, f'{base_name}.pdf')

            # --- ЭТАП 2: Конвертация Markdown в .tex с помощью Pandoc ---
            pandoc_to_tex_command = [
                'pandoc',
                '--filter', str(MERMAID_FILTER_PATH),
                '--lua-filter', str(MATH_FILTER_PATH),
                '--from=gfm-yaml_metadata_block+tex_math_dollars+raw_tex',
                '--to=latex',
                '--pdf-engine=xelatex', '--include-in-header', header_path,
                '--variable', f'title={title}',
                '--variable', f'author={author_string}',
                '--variable', f'date={date_string}',
                '--variable', 'documentclass=article',
                '--variable', 'geometry:margin=2cm',
                '-o', tex_path
            ]
            if re.search(r'^# ', markdown_string, re.MULTILINE):
                pandoc_to_tex_command.append('--toc')

            pandoc_process = subprocess.run(
                pandoc_to_tex_command, input=markdown_string.encode('utf-8'), capture_output=True
            )
            if pandoc_process.returncode != 0:
                raise RuntimeError(f"Ошибка Pandoc при конвертации в .tex: {pandoc_process.stderr.decode('utf-8', 'ignore')}")

            # --- ЭТАП 3: Постобработка .tex файла для исправления артефактов Pandoc ---
            if not os.path.exists(tex_path):
                raise RuntimeError(f"Pandoc не смог создать .tex файл. Stderr: {pandoc_process.stderr.decode('utf-8', 'ignore')}")

            with open(tex_path, 'r', encoding='utf-8') as f:
                tex_content = f.read()
            
            # Убираем ошибочную обертку \[ ... \] вокруг окружений amsmath
            math_envs = r'(?:align|gather|equation|multline)'
            pattern = re.compile(
                r'\\\[\s*(\\begin\{' + math_envs + r'\*?\}.*?\\end\{' + math_envs + r'\*?\})\s*\\\]',
                re.DOTALL
            )
            tex_content_fixed = pattern.sub(r'\1', tex_content)

            with open(tex_path, 'w', encoding='utf-8') as f:
                f.write(tex_content_fixed)

            # --- ЭТАП 4: Компиляция исправленного .tex в PDF ---
            compile_command = [
                'latexmk',
                '-file-line-error',
                '-pdf',
                '-xelatex',
                '-interaction=nonstopmode',
                f'-output-directory={temp_dir}',
                tex_path
            ]
            compile_process = subprocess.run(compile_command, capture_output=True, text=True, encoding='utf-8', errors='ignore')

            if not os.path.exists(pdf_path) or compile_process.returncode != 0:
                log_content = "Log file not found."
                log_path = os.path.join(temp_dir, f'{base_name}.log')
                if os.path.exists(log_path):
                    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                        log_content = f.read()

                fatal_error_match = re.search(r"^!.*$", log_content, re.MULTILINE)
                if fatal_error_match:
                    error_start_index = fatal_error_match.start()
                    context_end_index = log_content.find('\n\n', error_start_index)
                    if context_end_index == -1: context_end_index = error_start_index + 500
                    error_message = log_content[error_start_index:context_end_index].strip()
                else:
                    error_message = "Фатальная ошибка не найдена в .log, но компиляция не удалась. Конец лога:\n" + log_content[-2000:]
                
                process_output = (compile_process.stdout or "No stdout.") + "\n" + (compile_process.stderr or "No stderr.")
                error_header = "PDF-файл не был создан." if not os.path.exists(pdf_path) else "Компиляция PDF завершилась некорректно."
                
                raise RuntimeError(
                    f"Финальная ошибка: {error_header}\n\n"
                    f"--- КЛЮЧЕВАЯ ОШИБКА ИЗ ЛОГА ---\n{error_message}\n\n"
                    f"--- ВЫВОД LATEXMK (stdout/stderr) ---\n{process_output[-2000:]}"
                )

            with open(pdf_path, 'rb') as f:
                return io.BytesIO(f.read())
        finally:
            # Эта логика выполнится всегда, даже если в try возникнет ошибка.
            cleanup_log_file = '/tmp/pandoc_cleanup.log'
            if os.path.exists(cleanup_log_file):
                try:
                    with open(cleanup_log_file, 'r', encoding='utf-8') as f:
                        files_to_delete = f.readlines()
                    
                    for file_path in files_to_delete:
                        path = file_path.strip()
                        if path:  # Убедимся, что строка не пустая
                            try:
                                os.remove(path)
                                logger.debug(f"Успешно удален временный файл Mermaid: {path}")
                            except FileNotFoundError:
                                # Файл уже удален, это не ошибка
                                logger.warning(f"Временный файл Mermaid не найден для удаления: {path}")
                            except Exception as e:
                                # Логируем другие возможные ошибки при удалении
                                logger.error(f"Ошибка при удалении временного файла {path}: {e}")
                    
                    # После обработки удаляем сам файл лога, чтобы он не рос бесконечно
                    os.remove(cleanup_log_file)
                except Exception as e:
                    logger.error(f"Не удалось обработать или удалить файл лога очистки {cleanup_log_file}: {e}")

async def convert_md_to_pdf_pandoc(markdown_string: str, title: str, contributors: list | None = None, last_modified_date: str | None = None) -> io.BytesIO:
    """Асинхронная обертка для конвертации Markdown в PDF с помощью pandoc."""
    return await asyncio.to_thread(_convert_md_to_pdf_pandoc_sync, markdown_string, title, contributors, last_modified_date)


async def _prepare_html_with_katex(content: str, page_title: str) -> str:
    """
    Prepares a self-contained HTML document with a navigation panel, client-side rendering
    for LaTeX (using KaTeX), and Mermaid diagrams. This is the definitive, feature-complete version.
    """
    
    # --- Step 1: Isolate all valid math blocks with the robust regex ---
    latex_formulas = []
    def store_and_replace_latex(match):
        placeholder = f"<!--KATEX_PLACEHOLDER_{len(latex_formulas)}-->"
        latex_formulas.append(match.group(0))
        return placeholder

    latex_regex = r'(\$\$.*?\$\$|\$[^$\n]*?\$)'
    content_with_placeholders = re.sub(latex_regex, store_and_replace_latex, content, flags=re.DOTALL)

    # --- Step 2: Render the Markdown into an initial HTML string ---
    md = MarkdownIt("commonmark", {"html": True, "linkify": True, "typographer": True}).enable('table')
    html_content = md.render(content_with_placeholders)

    # --- Step 3: Generate Navigation Panel and Add IDs to Headers ---
    soup = BeautifulSoup(html_content, 'html.parser')
    headings = soup.find_all(['h1', 'h2', 'h3'])
    toc_items = []
    used_ids = set()

    for heading in headings:
        text = heading.get_text()
        slug_base = re.sub(r'[^\w\s-]', '', text.lower()).strip().replace(' ', '-')
        slug = slug_base
        counter = 1
        # Ensure the ID is unique
        while slug in used_ids:
            slug = f"{slug_base}-{counter}"
            counter += 1
        
        used_ids.add(slug)
        heading['id'] = slug
        
        level = int(heading.name[1]) # Gets the number from 'h1', 'h2', etc.
        toc_items.append({'level': level, 'text': text, 'id': slug})

    # Build the TOC HTML
    toc_html = '<nav class="toc"><h4>Содержание</h4><ul>'
    for item in toc_items:
        toc_html += f'<li class="toc-level-{item["level"]}"><a href="#{item["id"]}">{item["text"]}</a></li>'
    toc_html += '</ul></nav>'

    # Get the HTML with the newly added IDs in the header tags
    html_content_with_ids = str(soup)

    # --- Step 4: Process and re-insert the stored math formulas ---
    processed_formulas = []
    for formula_string in latex_formulas:
        is_display = formula_string.startswith('$$')
        content_start, content_end = (2, -2) if is_display else (1, -1)
        original_content = formula_string[content_start:content_end].strip()

        if is_display and ('\n' in original_content or r'\atop' in original_content):
            temp_content = original_content.replace(r'\atop', r'\\')
            original_content = f"\\begin{{gathered}}\n{temp_content}\n\\end{{gathered}}"

        protected_blocks = []
        def protect_text_blocks(m):
            placeholder = f"__TEXT_BLOCK_{len(protected_blocks)}__"
            protected_blocks.append(m.group(0))
            return placeholder
        
        temp_content = re.sub(r'\\text\{.*?\}', protect_text_blocks, original_content, flags=re.DOTALL)
        temp_content = re.sub(r'([\u0400-\u04FF]+(?:[\s.,][\u0400-\u04FF]+)*)', r'\\text{\1}', temp_content)
        for i, block in enumerate(protected_blocks):
            temp_content = temp_content.replace(f"__TEXT_BLOCK_{i}__", block)
        
        final_content = html.escape(temp_content)

        if is_display:
            processed_formulas.append(f'$${final_content}$$')
        else:
            processed_formulas.append(f'${final_content}$')

    # Re-insert into the HTML that already has header IDs
    final_html_content = html_content_with_ids
    for i, formula in enumerate(processed_formulas):
        placeholder = f"<!--KATEX_PLACEHOLDER_{i}-->"
        final_html_content = final_html_content.replace(placeholder, formula)

    # --- Step 5: Final preparation and templating ---
    final_html_content = final_html_content.replace(
        '<pre><code class="language-mermaid">', '<pre class="mermaid">'
    ).replace('</code></pre>', '</pre>')

    full_html_doc = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{page_title}</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css" integrity="sha384-n8MVd4RsNIU0tAv4ct0nTaAbDJwPJzDEaqSD1odI+WdtXRGWt2kTvGFasHpSy3SV" crossorigin="anonymous">
    <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js" integrity="sha384-XjKyOOlGwcjNTAIQHIpgOno0Hl1YQqzUOEleOLALmuqehneUG+vnGctmUb0ZY0l8" crossorigin="anonymous"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js" integrity="sha384-+VBxd3r6XgURycqtZ117nYw44OOcIax56Z4dCRWbxyPt0Koah1uHoK0o4+/RRE05" crossorigin="anonymous" onload="renderMathInElement(document.body, {{ delimiters: [ {{left: '$$', right: '$$', display: true}}, {{left: '$', right: '$', display: false}} ], throwOnError: false }});"></script>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        :root {{
            --bg-color: #ffffff; --text-color: #24292e; --link-color: #0366d6;
            --border-color: #eaecef; --code-bg-color: #f6f8fa;
        }}
        html {{ scroll-behavior: smooth; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; 
            line-height: 1.6; margin: 0 auto; padding: 20px 20px 20px 300px;
            max-width: 800px; 
            background-color: var(--bg-color); color: var(--text-color);
        }}
        @media (prefers-color-scheme: dark) {{
            :root:not(.light-theme) {{
                --bg-color: #0d1117; --text-color: #c9d1d9; --link-color: #58a6ff;
                --border-color: #30363d; --code-bg-color: #161b22;
            }}
        }}
        .toc {{
            position: fixed;
            top: 20px;
            left: 20px;
            width: 240px;
            max-height: 90vh;
            overflow-y: auto;
            padding: 16px;
            background-color: var(--code-bg-color);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            font-size: 14px;
        }}
        .toc h4 {{
            margin-top: 0;
            margin-bottom: 10px;
            font-size: 16px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 8px;
        }}
        .toc ul {{
            list-style-type: none;
            padding: 0;
            margin: 0;
        }}
        .toc li a {{
            text-decoration: none;
            color: var(--text-color);
            display: block;
            padding: 4px 0;
            border-radius: 4px;
        }}
        .toc li a:hover {{
            background-color: var(--border-color);
        }}
        .toc .toc-level-2 {{ margin-left: 15px; }}
        .toc .toc-level-3 {{ margin-left: 30px; }}

        @media (max-width: 1200px) {{
            .toc {{ display: none; }}
            body {{ padding: 20px; }}
        }}

        a {{ color: var(--link-color); }}
        pre {{ background-color: var(--code-bg-color); padding: 16px; overflow: auto; border-radius: 6px; position: relative; border: 1px solid var(--border-color); }}
        code {{ font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace; }}
        table {{ border-collapse: collapse; width: 100%; margin: 1em 0; border: 1px solid var(--border-color); }}
        th, td {{ border: 1px solid var(--border-color); padding: 6px 13px; text-align: left; }}
        tr:nth-child(2n) {{ background-color: var(--code-bg-color); }}
        h1, h2, h3, h4, h5, h6 {{ border-bottom: 1px solid var(--border-color); padding-bottom: .3em; margin-top: 24px; margin-bottom: 16px; }}
        .copy-btn {{
            position: absolute; top: 8px; right: 8px; padding: 4px 8px; font-size: 12px;
            background-color: #e1e4e8; color: #24292e; border: 1px solid #d1d5da;
            border-radius: 6px; cursor: pointer; opacity: 0; transition: opacity 0.2s;
        }}
        pre:hover .copy-btn {{ opacity: 1; }}
        @media (prefers-color-scheme: dark) {{ .copy-btn {{ background-color: #21262d; color: #c9d1d9; border-color: #30363d; }} }}
    </style>
</head>
<body>
    {toc_html}
    <main>{final_html_content}</main>
    <script>
        document.addEventListener("DOMContentLoaded", function() {{
            if (typeof mermaid !== 'undefined') mermaid.initialize({{ startOnLoad: true }});
            document.querySelectorAll('pre > code').forEach(function(codeBlock) {{
                var pre = codeBlock.parentElement;
                if (!pre) return;
                var button = document.createElement('button');
                button.className = 'copy-btn'; button.textContent = 'Copy';
                button.setAttribute('aria-label', 'Copy code to clipboard');
                button.addEventListener('click', function() {{
                    navigator.clipboard.writeText(codeBlock.innerText).then(function() {{
                        button.textContent = 'Copied!';
                        setTimeout(function() {{ button.textContent = 'Copy'; }}, 2000);
                    }});
                }});
                pre.appendChild(button);
            }});
        }});
    </script>
</body>
</html>"""
    return full_html_doc
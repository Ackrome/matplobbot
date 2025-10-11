import logging
import asyncio
import sys
import subprocess
import io
import contextlib
import tempfile
import shutil
import glob
import traceback
import re
import os
import json
import base64
import hashlib
from urllib.parse import quote
import aiohttp
import aiofiles
from PIL import Image
import datetime
import html # Added for HTML escaping
from bs4 import BeautifulSoup
from telegraph.aio import Telegraph
from aiogram.types import Message, CallbackQuery, FSInputFile, BufferedInputFile, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder
import markdown
from markdown_it import MarkdownIt

from . import database
import matplobblib
from . import keyboards as kb
from . import github_service

logger = logging.getLogger(__name__)

# --- Constants ---
# This new constant contains all the packages and settings needed by BOTH
# single formula rendering AND the full PDF document generation.
# This is the implementation of your excellent suggestion.
PANDOC_HEADER_INCLUDES = r"""
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{amsfonts}
\usepackage{graphicx}
\usepackage{mathrsfs}
\usepackage{color}
\usepackage{mhchem}
\usepackage{xcolor}
\usepackage{newunicodechar}
\usepackage{mathtools}
\usepackage{fontspec}      % The core of XeLaTeX font handling
\usepackage{babel}         % Language-specific settings
\usepackage{tikz,pgfplots}
\usepackage{blindtext}
\newunicodechar{∂}{\partial}
\newunicodechar{Δ}{\Delta}
"""

# The preamble for single formulas (this should now also be updated for consistency)
LATEX_PREAMBLE = r"""
\documentclass[12pt,varwidth=500pt]{standalone}
\usepackage[utf8]{inputenc}
\usepackage[T2A]{fontenc}
\usepackage[russian]{babel}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{amsfonts}
\usepackage{graphicx}
\usepackage{mathrsfs}
\usepackage{color}
\usepackage{mhchem}
\usepackage{tikz,pgfplots}
\usepackage{blindtext}
\usepackage{xcolor}
\usepackage{newunicodechar}
\newunicodechar{∂}{\partial}
\newunicodechar{Δ}{\Delta}
\begin{document}
"""

LATEX_POSTAMBLE = r"\end{document}"
MD_LATEX_PADDING = 15

# --- HTML Conversion ---
def convert_html_to_telegram_html(html_content: str) -> str:
    """Converts generic HTML to Telegram-supported HTML."""
    # This is a simplified converter. For complex HTML, a library like `beautifulsoup4` would be better.
    # The order of replacements is important.
    
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
def _pmatrix_hline_fixer(match: re.Match) -> str:
    """
    Callback for re.sub to replace a pmatrix environment with an array environment
    if the pmatrix contains a \\hline command, which is not supported by pmatrix.
    """
    matrix_content = match.group(1)
    # Check if \hline is present inside the matched pmatrix content
    if r'\hline' in matrix_content:
        # \hline is not supported by pmatrix, so we convert it to a compatible array.
        # To determine the number of columns, we find the line with the maximum number of alignment tabs (&).
        lines = matrix_content.strip().split(r'\\')
        num_cols = 0
        for line in lines:
            # This is a simple heuristic to avoid counting '&' inside other commands like \text{...}.
            # It's not foolproof but covers many common cases.
            clean_line = re.sub(r'\\text\{.*?\}', '', line)
            # Count alignment tabs in the current line and add 1 for the number of columns.
            current_cols = clean_line.count('&') + 1
            if current_cols > num_cols:
                num_cols = current_cols
        
        # Fallback to 1 column if no '&' are found (unlikely for a matrix with \hline, but safe).
        if num_cols == 0 and len(lines) > 0:
            num_cols = 1
        
        if num_cols > 0:
            # Create the column specification string (e.g., 'ccc' for 3 columns).
            col_spec = 'c' * num_cols
            # Reconstruct the matrix using the array environment, wrapped in parentheses.
            return f'\\left(\\begin{{array}}{{{col_spec}}}{matrix_content}\\end{{array}}\\right)'
    
    # If no \hline is found, return the original pmatrix environment unchanged.
    return match.group(0)
# --- LaTeX Rendering ---
def _render_latex_sync(latex_string: str, padding: int, dpi: int, is_display_override: bool | None = None) -> io.BytesIO:
    """Синхронная функция для рендеринга LaTeX в PNG с использованием latex и dvipng, с добавлением отступов."""

    # Для команды /latex по умолчанию считаем формулу блочной (display) для лучшего качества.
    # Для обработки markdown флаг передается явно.
    is_display = is_display_override if is_display_override is not None else True

    # Сначала просто убираем пробелы по краям
    processed_latex = latex_string.strip()

    # Heuristic fix for a common user error: placing \tag after the environment.
    # This moves the tag inside, right before the \end{...} command.
    processed_latex = re.sub(
        r'(\\end\{([a-zA-Z\*]+)\})(\s*\\tag\{.*?\})',
        r'\3 \1',
        processed_latex,
        flags=re.DOTALL
    )

    # Heuristic fix for primitive TeX commands like \atop used after an environment.
    processed_latex = re.sub(
        r'(\\end\{([a-zA-Z\*]+)\})(\s*\\atop\s*(\\text\{.*?\}))',
        r'\\ \4 \1',
        processed_latex,
        flags=re.DOTALL
    )
    
    # --- NEW FIX START ---
    # Heuristic fix for pmatrix environments containing \hline.
    # The pmatrix environment does not support \hline, causing a compilation error.
    # This fix replaces the pmatrix with a functionally equivalent array environment
    # which does support \hline.
    processed_latex = re.sub(
        r'\\begin{pmatrix}(.*?)\\end{pmatrix}', 
        _pmatrix_hline_fixer, 
        processed_latex, 
        flags=re.DOTALL
    )
    # --- NEW FIX END ---

    # Более интеллектуальная обработка переносов строк.
    if not re.search(r'\\begin\{[a-zA-Z\*]+\}.*?\\end\{[a-zA-Z\*]+\}', processed_latex, re.DOTALL):
        processed_latex = processed_latex.replace('\n', ' ')
    else:
        pass

    s = processed_latex

    # Список окружений, которые сами создают математический режим.
    standalone_math_envs = [
        'equation', 'equation*', 'align', 'align*', 'gather', 'gather*',
        'multline', 'multline*', 'displaymath', 'math', 'alignat', 'alignat*',
        'flalign', 'flalign*', 'gathered' # Added gathered to the list
    ]
    # Проверяем, начинается ли строка с \begin{...}
    starts_with_standalone_env = False
    match = re.match(r'\\begin\{([a-zA-Z\*]+)\}', s.strip())
    if match and match.group(1) in standalone_math_envs:
        starts_with_standalone_env = True

    is_already_math_env = (
        (s.startswith('$') and s.endswith('$')) or
        (s.startswith('$$') and s.endswith('$$')) or
        (s.startswith(r'\[') and s.endswith(r'\]')) or
        starts_with_standalone_env
    )
    
    contains_tag = r'\tag' in s
    
    # The \tag command is only for display math, so we force display mode.
    if contains_tag:
        is_display = True

    # Only wrap the expression if it isn't already in a math environment
    if not is_already_math_env:
        if contains_tag:
            processed_latex = f'\\begin{{equation*}}\n{processed_latex}\n\\end{{equation*}}'
        else:
            if is_display:
                processed_latex = f'\\[{processed_latex}\\]'
            else:
                processed_latex = f'${processed_latex}$'
                
    full_latex_code = LATEX_PREAMBLE + processed_latex + LATEX_POSTAMBLE

    with tempfile.TemporaryDirectory() as temp_dir:
        tex_path = os.path.join(temp_dir, 'formula.tex')
        log_path = os.path.join(temp_dir, 'formula.log')
        dvi_path = os.path.join(temp_dir, 'formula.dvi')
        png_path = os.path.join(temp_dir, 'formula.png')

        with open(tex_path, 'w', encoding='utf-8') as f:
            f.write(full_latex_code)

        # --- Запуск LaTeX ---
        process = subprocess.run(
            ['latex', '-interaction=nonstopmode', '-output-directory', temp_dir, tex_path],
            capture_output=True, text=True, encoding='utf-8', errors='ignore'
        )

        # --- Проверка на ошибки LaTeX ---
        if not os.path.exists(dvi_path) or process.returncode != 0:
            error_message = "Неизвестная ошибка LaTeX."
            if os.path.exists(log_path):
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as log_file:
                    log_content = log_file.read()
                    error_lines = [line for line in log_content.split('\n') if line.startswith('! ')]
                    if error_lines:
                        error_message = error_lines[0].strip()
                    else:
                       error_message = "...\n" + "\n".join(log_content.split('\n')[-20:])
                       raise ValueError(f"Ошибка компиляции LaTeX:\n{error_message}")

        # --- Запуск dvipng для конвертации DVI в PNG ---
        dvipng_process = subprocess.run(
            ['dvipng', '-D', str(dpi), '-T', 'tight', '-bg', 'Transparent', '-o', png_path, dvi_path],
            capture_output=True, text=True, encoding='utf-8', errors='ignore'
        )
        
        if dvipng_process.returncode != 0 or not os.path.exists(png_path):
            raise RuntimeError(f"Ошибка dvipng: {dvipng_process.stderr}")

        # --- Добавление отступов и выравнивание с помощью Pillow ---
        with Image.open(png_path) as img:
            if is_display:
                target_width = 600
                final_width = max(img.width + 2 * padding, target_width)
                final_height = img.height + 2 * padding
                new_img = Image.new("RGBA", (final_width, final_height), (0, 0, 0, 0))
                paste_x = (final_width - img.width) // 2
                paste_y = padding
                new_img.paste(img, (paste_x, paste_y))
            else:
                final_width = img.width + 2 * padding
                final_height = img.height + 2 * padding
                new_img = Image.new("RGBA", (final_width, final_height), (0, 0, 0, 0))
                new_img.paste(img, (padding, padding))

            buf = io.BytesIO()
            new_img.save(buf, format='PNG')
            buf.seek(0)
            return buf
                    
async def render_latex_to_image(latex_string: str, padding: int, dpi:int = 300, is_display_override: bool | None = None) -> io.BytesIO:
    """Асинхронная обертка для рендеринга LaTeX, выполняемая в отдельном потоке."""
    return await asyncio.to_thread(_render_latex_sync, latex_string, padding, dpi, is_display_override)

# --- Mermaid Rendering ---
def _render_mermaid_sync(mermaid_code: str) -> io.BytesIO:
    """Синхронная функция для рендеринга Mermaid в PNG с использованием mmdc."""
    with tempfile.TemporaryDirectory() as temp_dir:
        input_path = os.path.join(temp_dir, 'diagram.mmd')
        output_path = os.path.join(temp_dir, 'diagram.png')

        with open(input_path, 'w', encoding='utf-8') as f:
            f.write(mermaid_code)

        # Dynamically find the mmdc executable path
        mmdc_path = shutil.which('mmdc')
        if not mmdc_path:
            raise FileNotFoundError("Mermaid CLI (mmdc) not found in PATH. Please ensure it is installed correctly in the Docker image.")

        # Запуск Mermaid CLI (mmdc)
        process = subprocess.run(
            [
                mmdc_path, '-p', '/app/bot/puppeteer-config.json',
                '-i', input_path, '-o', output_path, '-b', 'transparent'
            ],
            capture_output=True, text=True, encoding='utf-8', errors='ignore'
        )

        if process.returncode != 0 or not os.path.exists(output_path):
            error_output = process.stderr or process.stdout or "Unknown error."
            # Очищаем вывод от лишней информации Puppeteer
            clean_error = re.sub(r'\(node:\d+\) \[[^\]]+\] ', '', error_output)
            raise ValueError(f"Ошибка рендеринга Mermaid:\n{clean_error.strip()}")

        # Читаем результат в буфер
        with open(output_path, 'rb') as f:
            buf = io.BytesIO(f.read())
        
        buf.seek(0)
        return buf

async def render_mermaid_to_image(mermaid_code: str) -> io.BytesIO:
    """Асинхронная обертка для рендеринга Mermaid, выполняемая в отдельном потоке."""
    return await asyncio.to_thread(_render_mermaid_sync, mermaid_code)

def _convert_md_to_pdf_pandoc_sync(markdown_string: str, title: str, contributors: list | None = None, last_modified_date: str | None = None) -> io.BytesIO:
    """
    Окончательная, надежная функция для конвертации Markdown в PDF.
    Использует метаданные (авторы, дата) для создания более информативного документа.
    """
    # Форматируем авторов в виде кликабельных ссылок для Pandoc
    if contributors:
        # Pandoc понимает синтаксис Markdown в метаданных и превратит его в \href{}{} в LaTeX
        # author_links = [f"[{c['login']}]({c['html_url']})" for c in contributors]
        author_links = [r"\href{"+ f"{c['html_url']}" + r"}{" + f"{c['login']}" + r"}" for c in contributors]
        author_string = ", ".join(author_links)
    else:
        author_string = "Matplobbot" # Запасной вариант

    # Используем дату последнего изменения или текущую дату как запасной вариант
    date_string = last_modified_date or datetime.datetime.now().strftime("%d %B %Y")
    
    cleanup_log_path = '/tmp/pandoc_cleanup.log'
    if os.path.exists(cleanup_log_path):
        os.remove(cleanup_log_path)

    with tempfile.TemporaryDirectory() as temp_dir:
        # A minimal, correct header for XeLaTeX
        header_path = os.path.join(temp_dir, 'header.tex')
        with open(header_path, 'w', encoding='utf-8') as f:
            # PANDOC_HEADER_INCLUDES must be defined globally and correctly for XeLaTeX
            f.write(PANDOC_HEADER_INCLUDES)

        try:
            base_name = 'document'
            tex_path = os.path.join(temp_dir, f'{base_name}.tex')
            pdf_path = os.path.join(temp_dir, f'{base_name}.pdf')

            # --- STAGE 1: Convert Markdown to a standalone .tex file ---
            pandoc_to_tex_command = [
                'pandoc', 
                '--filter', '/app/bot/pandoc_mermaid_filter.py',
                # --- NEW FIX: Add a Lua filter to sanitize math environments ---
                '--lua-filter', '/app/bot/pandoc_math_filter.lua',
                # --- END NEW FIX ---
                '--from=markdown+tex_math_dollars+raw_tex+escaped_line_breaks+backtick_code_blocks', '--to=latex',
                '--pdf-engine=xelatex', '--include-in-header', header_path,
                '--variable', 'lang=russian', '--variable', 'mainfont=DejaVu Serif',
                '--variable', 'sansfont=DejaVu Sans', '--variable', 'monofont=DejaVu Sans Mono',
                '--variable', f'title={title}', '--variable', f'author={author_string}',
                '--variable', f'date={date_string}', '--variable', 'documentclass=article',
                # --- ИЗМЕНЕНИЕ ЗДЕСЬ: Устанавливаем поля в 2см ---
                '--variable', 'geometry:margin=2cm',
                '-o', tex_path
            ]
            
            if re.search(r'^# ', markdown_string, re.MULTILINE):
                pandoc_to_tex_command.append('--toc')

            pandoc_process = subprocess.run(
                pandoc_to_tex_command, input=markdown_string.encode('utf-8'), capture_output=True
            )
            if pandoc_process.returncode != 0:
                raise RuntimeError(f"Ошибка Pandoc: {pandoc_process.stderr.decode('utf-8', 'ignore')}")

            # --- STAGE 2: Sanitize the generated LaTeX code ---
            # --- STAGE 3: Compile with latexmk, the robust industry standard ---
            compile_command = [
                'latexmk',
                '-pdf',          # Explicitly demand a PDF as the final output
                '-xelatex',      # Use the correct, Unicode-aware engine. Removed '-f' to fail on errors.
                '-interaction=nonstopmode',
                f'-output-directory={temp_dir}',
                tex_path
            ]
            compile_process = subprocess.run(compile_command, capture_output=True, text=True, encoding='utf-8', errors='ignore')

            # --- DEFINITIVE ERROR CHECK: Trust the file, not the return code ---
            log_path = os.path.join(temp_dir, f'{base_name}.log')
            log_content = "Log file not found."
            compilation_successful = False
            if os.path.exists(log_path):
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    log_content = f.read()
                    # A successful latexmk run will have this line near the end.
                    if re.search(r"Output written on .*?\.pdf", log_content):
                        compilation_successful = True

            if not os.path.exists(pdf_path) or not compilation_successful:
                process_output = compile_process.stdout or "No stdout."
                error_header = "PDF-файл не был создан." if not os.path.exists(pdf_path) else "Компиляция PDF завершилась некорректно (неполный файл)."
                raise RuntimeError(f"Финальная ошибка: {error_header}\n--- STDOUT ---\n{process_output[-2000:]}\n--- LOG ---\n{log_content[-2000:]}")

            with open(pdf_path, 'rb') as f:
                return io.BytesIO(f.read())

        finally:
            # Cleanup logic
            if os.path.exists(cleanup_log_path):
                try:
                    with open(cleanup_log_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            file_path = line.strip()
                            if file_path and os.path.exists(file_path):
                                try: os.remove(file_path)
                                except OSError: pass
                    os.remove(cleanup_log_path)
                except Exception: pass
                
async def convert_md_to_pdf_pandoc(markdown_string: str, title: str, contributors: list | None = None, last_modified_date: str | None = None) -> io.BytesIO:
    """Асинхронная обертка для конвертации Markdown в PDF с помощью pandoc."""
    return await asyncio.to_thread(_convert_md_to_pdf_pandoc_sync, markdown_string, title, contributors, last_modified_date)

async def _resolve_wikilinks(content: str, repo_path: str, all_repo_files: list[str], target_format: str = 'md') -> str:
    """
    Finds all [[wikilinks]] in the content and replaces them with standard
    links for the specified target format ('md' or 'latex').
    Handles both [[Page Name]] and [[Page Name|display text]] syntaxes.
    """
    if not all_repo_files:
        return content

    # Create a mapping from "wikilink-friendly" names to full paths
    # e.g., "my page" -> "path/to/My Page.md"
    file_map = {os.path.splitext(os.path.basename(f))[0].lower(): f for f in all_repo_files}

    def replace_wikilink(match):
        # The content inside [[...]]
        inner_content = match.group(1).strip()
        
        # Split by '|' to separate file name from display text
        parts = inner_content.split('|', 1)
        file_name_part = parts[0].strip()
        display_text = parts[1].strip() if len(parts) > 1 else file_name_part

        # Find a matching file in the map using the file name part
        found_path = file_map.get(file_name_part.lower())

        if found_path:
            # Construct the full URL to the file on GitHub
            # We use quote() to properly encode spaces and other special characters in the path
            url = f"https://github.com/{repo_path}/blob/{github_service.MD_SEARCH_BRANCH}/{quote(found_path)}"

            if target_format == 'latex':
                # For LaTeX/PDF, use \href{url}{text}. We need to escape special LaTeX chars in text.
                # A simple escape for common characters.
                escaped_display_text = display_text.replace('&', r'\&').replace('%', r'\%').replace('$', r'\$').replace('#', r'\#').replace('_', r'\_').replace('{', r'\{').replace('}', r'\}').replace('~', r'\textasciitilde ').replace('^', r'\textasciicircum ')
                # --- NEW FIX: Also escape special characters in the URL for LaTeX ---
                # Characters like _, #, %, & can break the \href command if not escaped.
                # The `url` is already URL-encoded, but LaTeX needs its own escaping.
                escaped_url = url.replace('\\', r'\textbackslash ').replace('&', r'\&').replace('%', r'\%').replace('$', r'\$').replace('#', r'\#').replace('_', r'\_').replace('{', r'\{').replace('}', r'\}').replace('~', r'\textasciitilde{}')
                return f"\\href{{{escaped_url}}}{{{escaped_display_text}}}"
            else: # Default to Markdown
                return f"[{display_text}]({url})"
        else:
            # If no file is found, return the original wikilink text but not as a link.
            # This makes it clear that the link is broken.
            return f"_{display_text}_"

    # This regex finds [[wikilinks]] but avoids grabbing the middle of other links.
    # It looks for [[ followed by any characters except ] until it finds ]].
    wikilink_regex = r"\[\[([^\]]+)\]\]"
    
    resolved_content = re.sub(wikilink_regex, replace_wikilink, content)
    return resolved_content


# --- Code Execution ---
async def execute_code_and_send_results(message: Message, code_to_execute: str):

    """Helper function to execute code and send results back to the user."""
    output_capture = io.StringIO()
    execution_error = None
    temp_dir = None
    original_cwd = os.getcwd()
    rich_outputs = []
    exec_globals = { 
        "asyncio": asyncio,
        "message": message,
        "os": os,
        "sys": sys,
        "__builtins__": __builtins__,
    }

    # 2. Попытка импорта "rich display" библиотек и внедрение кастомных функций
    try:
        from IPython.display import display as ipython_display, Markdown, HTML
        

        def custom_display(*objs, **kwargs):
            """Перехватывает вызовы display, обрабатывает Markdown/HTML и делегирует остальное."""
            for obj in objs:
                if isinstance(obj, Markdown):
                    html_content = markdown.markdown(obj.data, extensions=['fenced_code'])
                    tg_html = convert_html_to_telegram_html(html_content)
                    rich_outputs.append({'type': 'html', 'content': tg_html})
                elif isinstance(obj, HTML):
                    tg_html = convert_html_to_telegram_html(obj.data)
                    rich_outputs.append({'type': 'html', 'content': tg_html})
                else:
                    # For other objects, capture their string representation.
                    # This avoids unexpected behavior from ipython_display outside an IPython kernel.
                    output_capture.write(repr(obj) + '\n')

        # Внедряем наши функции и классы в окружение для выполнения 
        exec_globals['display'] = custom_display 
        exec_globals['Markdown'] = Markdown
        exec_globals['HTML'] = HTML

    except ImportError:
        logger.warning("IPython или markdown не установлены. Rich display отключен для /execute.")
        pass

    # 3. Выполнение кода пользователя в контролируемом окружении
    try:
        temp_dir = tempfile.mkdtemp()
        os.chdir(temp_dir)

        with contextlib.redirect_stdout(output_capture), contextlib.redirect_stderr(output_capture):
            local_scope = {} # Словарь для получения результата exec (самой функции)
            wrapped_code = f"async def __exec_code():\n"
            wrapped_code += "".join([f"    {line}\n" for line in code_to_execute.splitlines()])
            
            exec(wrapped_code, exec_globals, local_scope)
            await local_scope["__exec_code"]()
            
    except Exception:
        execution_error = f"--- ОШИБКА ВЫПОЛНЕНИЯ ---\n{traceback.format_exc()}"
    finally:
        os.chdir(original_cwd)

        # --- Отправка результатов ---
        if execution_error:
            await message.answer(f"```\n{execution_error}\n```", parse_mode='markdown')

        # Отправляем rich-вывод (HTML)
        for output in rich_outputs: 
            content_to_send = output['content'] # This is the raw HTML or Markdown string
            parse_mode = None # Default to no parse mode, will be set based on type

            if output['type'] == 'markdown':
                # Convert Markdown to HTML first
                
                content_to_send = markdown.markdown(content_to_send, extensions=['fenced_code'])
                # Then apply Telegram-specific HTML conversion for basic tags
                content_to_send = convert_html_to_telegram_html(content_to_send)
                parse_mode = 'HTML'
            elif output['type'] == 'html':
                # For explicit HTML objects, try to send raw HTML and let Telegram parse it.
                # convert_html_to_telegram_html is NOT applied here, relying on Telegram's parser.
                parse_mode = 'HTML'

            if content_to_send:
                try:
                    await message.answer(content_to_send, parse_mode=parse_mode)
                except TelegramBadRequest as e:
                    logger.warning(f"TelegramBadRequest when sending rich output (type: {output['type']}): {e}. Attempting to send as file.")
                    # If Telegram HTML fails, save as .html file and send
                    file_name = f"output_{output['type']}_{len(rich_outputs)}.html"
                    file_path = os.path.join(temp_dir, file_name)
                    
                    # Ensure the content written to file is the original, full HTML
                    # For markdown, this would be the markdown-converted HTML
                    # For HTML, this would be the raw HTML from obj.data
                    content_to_write = output['content'] # Original content
                    if output['type'] == 'markdown':
                        
                        content_to_write = markdown.markdown(content_to_write, extensions=['fenced_code'])

                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content_to_write)
                    try:
                        await message.answer_document(
                            document=FSInputFile(file_path),
                            caption=f"Вывод ({output['type']}) был отправлен как файл, так как он слишком сложен для отображения в Telegram."
                        )
                    except Exception as file_e:
                        logger.error(f"Failed to send rich output as file {file_path}: {file_e}")
                        await message.answer(f"Не удалось отправить rich-вывод как файл: {file_e}")
                except Exception as e:
                    logger.error(f"Unexpected error when sending rich output: {e}")
                    await message.answer(f"Произошла ошибка при отправке rich-вывода: {e}")

        # Ищем и отправляем сгенерированные изображения 
        image_files = [] 
        if temp_dir: 
            for ext in ['*.png', '*.jpg', '*.jpeg', '*.gif']:
                image_files.extend(glob.glob(os.path.join(temp_dir, ext)))
            
            for img_path in image_files:
                try:
                    await message.answer_photo(photo=FSInputFile(img_path))
                except Exception as e:
                    logger.error(f"Failed to send photo {img_path}: {e}")
                    await message.answer(f"Не удалось отправить изображение {os.path.basename(img_path)}: {e}")

        # Отправляем текстовый вывод, если он есть
        text_output = output_capture.getvalue()
        if text_output:
            if len(text_output) > 4096:
                await message.answer('Текстовый вывод слишком длинный, отправляю частями.')
                for x in range(0, len(text_output), 4096):
                    await message.answer(f"```\n{text_output[x:x+4096]}\n```", parse_mode='markdown')
            else:
                await message.answer(f"```\n{text_output}\n```", parse_mode='markdown')

        # Сообщение, если не было ни вывода, ни картинок, ни ошибок
        if not execution_error and not image_files and not text_output and not rich_outputs:
            await message.answer("Код выполнен успешно без какого-либо вывода.")

        # Очищаем временную директорию
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.error(f"Ошибка при удалении временной директории {temp_dir}: {e}")

        # Возвращаем основную клавиатуру
        await message.answer("Выполнение завершено.", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))

async def send_as_plain_text(message: Message, file_path: str, content: str):
    """Helper to send content as plain text, handling long messages."""
    header = f"Файл: `{file_path}` (простой текст)\n\n"
    
    await message.answer(header, parse_mode='markdown')
    # Send content in chunks
    if len(content) == 0:
        await message.answer("_(файл пуст)_", parse_mode='markdown')
        return

    for x in range(0, len(content), 4000): # Use a slightly smaller chunk size for safety with markdown ```
        chunk = content[x:x+4000]
        await message.answer(f"```\n{chunk}\n```", parse_mode='markdown')

async def send_as_document_from_url(message: Message, file_url: str, file_path: str):
    """Downloads a file from a URL by chunks and sends it as a document."""
    file_name = os.path.basename(file_path)
    status_msg = await message.answer(f"Загружаю файл `{file_name}`...", parse_mode='markdown')
    
    temp_file_path = None
    try:
        # Create a temporary file to store the download
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file_name}") as tmp_file:
            temp_file_path = tmp_file.name

        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as response:
                response.raise_for_status() # Raise an exception for bad status codes
                
                # Stream the download in chunks
                async with aiofiles.open(temp_file_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)
        
        # Send the downloaded file
        await message.answer_document(
            document=FSInputFile(temp_file_path, filename=file_name),
            caption=f"Файл: `{file_path}`",
            parse_mode='markdown'
        )
        await status_msg.delete()

    except Exception as e:
        logger.error(f"Failed to download/send file from {file_url}: {e}", exc_info=True)
        await status_msg.edit_text(f"Не удалось загрузить или отправить файл `{file_name}`. Ошибка: {e}")
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)

async def display_github_file(message: Message, user_id: int, repo_path: str, file_path: str, status_msg_to_delete: Message | None = None):
    """
    Fetches a file from GitHub and displays it, using Telegra.ph for Markdown files."""
    # The initial "Processing..." message is now sent from the handler.
    raw_url = f"https://raw.githubusercontent.com/{repo_path}/{github_service.MD_SEARCH_BRANCH}/{file_path}"

    # Check if it's a markdown file
    if file_path.lower().endswith('.md'):
        # --- Existing logic for Markdown files ---
        # This part fetches content as text and processes it.
        content = github_service.github_content_cache.get(file_path)
        if content is not None:
            logger.info(f"Cache hit for file content: {file_path}")
        else:
            logger.info(f"Cache miss for file content: {file_path}. Fetching from GitHub.")
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(raw_url) as response:
                        if response.status == 200:
                            content = await response.text(encoding='utf-8', errors='ignore')
                            github_service.github_content_cache[file_path] = content # Store in cache
                        else:
                            await message.answer(f"Не удалось загрузить файл. Ошибка: {response.status}")
                            return
            except Exception as e:
                await message.answer(f"Произошла ошибка при загрузке файла: {e}")
                return

        if content is None:
            await message.answer("Не удалось получить содержимое файла.")
            return

        # Get user settings to decide how to display the file
        settings = await database.get_user_settings(user_id)
        md_mode = settings.get('md_display_mode', 'md_file')

        # Option 1: .md file
        if md_mode == 'md_file':
            file_name = file_path.split('/')[-1]
            file_bytes = content.encode('utf-8')
            await message.answer_document(
                document=BufferedInputFile(file_bytes, filename=file_name),
                caption=f"Файл конспекта: `{file_path}`",
                parse_mode='markdown'
            )

        # Option 2: .pdf file
        elif md_mode == 'pdf_file':
            try:
                page_title = file_path.split('/')[-1].replace('.md', '')
                file_name = f"{page_title}.pdf"

                async with aiohttp.ClientSession() as session:
                    # --- WIKILINK INTEGRATION ---
                    all_repo_files = await github_service.get_all_repo_files_cached(repo_path, session)
                    resolved_content = await _resolve_wikilinks(content, repo_path, all_repo_files, target_format='latex')
                    # --- END WIKILINK INTEGRATION ---
                    contributors = await github_service.get_repo_contributors(repo_path, session)
                    last_modified_date = await github_service.get_file_last_modified_date(repo_path, file_path, session)
                    pdf_buffer = await convert_md_to_pdf_pandoc(resolved_content, page_title, contributors, last_modified_date)

                await message.answer_document(document=BufferedInputFile(pdf_buffer.getvalue(), filename=file_name), caption=f"PDF-версия конспекта: `{file_path}`", parse_mode='markdown')
            except Exception as e:
                logger.error(f"Ошибка при создании PDF для '{file_path}': {e}", exc_info=True)
                # --- NEW FIX: Truncate long error messages to avoid TelegramBadRequest ---
                error_message = str(e)
                max_len = 3900 # Even more safe to account for prefix text
                if len(error_message) > max_len:
                    truncated_error = error_message[:max_len] + "\n\n... (сообщение об ошибке было сокращено)"
                else:
                    truncated_error = error_message
                await message.answer(f"Произошла ошибка при создании PDF-файла: {truncated_error}. Отправляю как простой текст.")
                await send_as_plain_text(message, file_path, content) # Fallback
        # Option 3: .html file
        elif md_mode == 'html_file':
            try:
                page_title = file_path.split('/')[-1].replace('.md', '')
                # --- WIKILINK INTEGRATION ---
                async with aiohttp.ClientSession() as session:
                    all_repo_files = await github_service.get_all_repo_files_cached(repo_path, session)
                resolved_content = await _resolve_wikilinks(content, repo_path, all_repo_files, target_format='md')
                full_html_doc = await _prepare_html_with_katex(resolved_content, page_title)
                # --- END WIKILINK INTEGRATION ---

                file_bytes = full_html_doc.encode('utf-8')
                file_name = f"{page_title}.html"
                await message.answer_document(
                    document=BufferedInputFile(file_bytes, filename=file_name),
                    caption=f"HTML-версия конспекта: `{file_path}`",
                    parse_mode='markdown'
                )
            except Exception as e:
                logger.error(f"Ошибка при создании HTML-файла с KaTeX для '{file_path}': {e}", exc_info=True)
                await message.answer(f"Произошла ошибка при создании HTML-файла: {e}. Отправляю как простой текст.")
                await send_as_plain_text(message, file_path, content) # Fallback
        
        # Fallback for unknown mode
        else:
            logger.warning(f"Unknown md_display_mode '{md_mode}' for user {user_id}. Falling back to plain text.")
            await send_as_plain_text(message, file_path, content)
    else:
        # Not a markdown file, download and send as a document
        await send_as_document_from_url(message, raw_url, file_path)
    
    # Finally, delete the status message and show the main keyboard
    if status_msg_to_delete:
        try:
            await status_msg_to_delete.delete()
        except TelegramBadRequest:
            pass # Message might have been deleted already
    await message.answer("Выберите следующую команду:", reply_markup=kb.get_main_reply_keyboard(user_id))

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
        # Create a URL-friendly "slug" for the ID
        # --- WIKILINK FIX: Use original heading text for TOC, not slugified version ---
        # The slug is only for the 'id' attribute. The visible text should be original.
        # This was already correct, just adding a comment for clarity.
        # slug_base = re.sub(r'[^\w\s-]', '', text.lower()).strip().replace(' ', '-')
        # ...
        # toc_items.append({'level': level, 'text': text, 'id': slug})

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
        html {{ scroll-behavior: smooth; }} /* This enables smooth scrolling */
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; 
            line-height: 1.6; margin: 0 auto; padding: 20px 20px 20px 300px; /* Add left padding for TOC */
            max-width: 800px; 
            background-color: var(--bg-color); color: var(--text-color);
        }}
        @media (prefers-color-scheme: dark) {{
            :root:not(.light-theme) {{
                --bg-color: #0d1117; --text-color: #c9d1d9; --link-color: #58a6ff;
                --border-color: #30363d; --code-bg-color: #161b22;
            }}
        }}

        /* ----- Navigation Panel (TOC) Styles ----- */
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

        /* Responsive: Hide TOC on smaller screens */
        @media (max-width: 1200px) {{
            .toc {{ display: none; }}
            body {{ padding: 20px; }} /* Reset body padding */
        }}

        /* ----- General Element Styling ----- */
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

async def _prepare_html_from_markdown(content: str, settings: dict, file_path: str) -> tuple[str, list]:
    """
    A helper function that processes markdown content into a full HTML document.
    This logic is shared between 'html_file' and 'pdf_file' modes.
    Returns a tuple of (full_html_string, list_of_latex_formulas).
    """
    # 1. Find all LaTeX formulas, replace with placeholders, and store them.
    latex_formulas = []

    def store_latex_match(match):
        is_display = match.group(1) is not None
        code = match.group(1) if is_display else match.group(2)
        if code is not None:
            placeholder = f'<latex-placeholder id="{len(latex_formulas)}"></latex-placeholder>'
            latex_formulas.append({
                'code': code.strip(),
                'is_display': is_display,
                'placeholder': placeholder,
                'original': match.group(0)
            })
            return placeholder
        return match.group(0)

    latex_regex = r'\$\$(.*?)\$\$|(?<!\$)\$([^$]+)\$(?!\$)'
    content_with_placeholders = re.sub(latex_regex, store_latex_match, content, flags=re.DOTALL)

    # 2. Convert Markdown to HTML.
    html_with_placeholders = markdown.markdown(content_with_placeholders, extensions=['fenced_code', 'tables'])
    html_with_placeholders = html_with_placeholders.replace('<pre><code class="language-mermaid">', '<pre class="mermaid">').replace('</code></pre>', '</pre>')

    # 3. Asynchronously render formulas and get image URLs.
    padding = MD_LATEX_PADDING
    dpi = settings['latex_dpi']
    async with aiohttp.ClientSession() as session:
        async def render_and_upload(formula_data):
            try:
                if not formula_data['code']: return None
                current_padding = padding if formula_data['is_display'] else max(0, padding - 10)
                formula_key = f"{formula_data['code']}|{current_padding}|{dpi}|{formula_data['is_display']}"
                formula_hash = hashlib.sha1(formula_key.encode()).hexdigest()
                cached_url = await database.get_latex_cache(formula_hash)
                if cached_url: return cached_url

                image_buffer = await render_latex_to_image(formula_data['code'], current_padding, dpi, is_display_override=formula_data['is_display'])
                image_buffer.seek(0)
                image_url = await github_service.upload_image_to_github(image_buffer, session)
                if image_url: await database.add_latex_cache(formula_hash, image_url)
                return image_url
            except Exception as e:
                logger.warning(f"Failed to render/upload LaTeX ('{formula_data['code']}'): {e}")
                return None

        semaphore = asyncio.Semaphore(5)
        async def guarded_render(formula_data):
            async with semaphore:
                return await render_and_upload(formula_data)

        tasks = [guarded_render(f) for f in latex_formulas]
        image_urls = await asyncio.gather(*tasks)

    # 4. Replace placeholders with <img> tags.
    html_content = html_with_placeholders
    for i, formula_data in enumerate(latex_formulas):
        url = image_urls[i]
        if url:
            if formula_data['is_display']:
                replacement = f'<figure><img src="{url}" style="max-width: 80%; height: auto; display: block; margin-left: auto; margin-right: auto;"></figure>'
            else:
                replacement = f'<img src="{url}" style="height: 1.8em; vertical-align: -0.6em;">'
        else:
            replacement = f'<i>[Ошибка рендеринга LaTeX: {formula_data["original"]}]</i>'
        html_content = html_content.replace(formula_data['placeholder'], replacement)

    # 5. Wrap in a full HTML document.
    page_title = file_path.split('/')[-1].replace('.md', '')
    full_html_doc = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{page_title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; margin: 0 auto; padding: 20px; max-width: 800px; }}
        img {{ max-width: 100%; height: auto; }}
        figure {{ margin: 1.5em 0; }}
        pre {{ background-color: #f6f8fa; padding: 16px; overflow: auto; border-radius: 6px; }}
        code {{ font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace; }}
        table {{ border-collapse: collapse; width: 100%; margin: 1em 0; border: 1px solid #dfe2e5; }}
        th, td {{ border: 1px solid #dfe2e5; padding: 6px 13px; }}
        tr {{ border-top: 1px solid #c6cbd1; }}
        tr:nth-child(2n) {{ background-color: #f6f8fa; }}
        h1, h2, h3, h4, h5, h6 {{ border-bottom: 1px solid #eaecef; padding-bottom: .3em; margin-top: 24px; margin-bottom: 16px; }}
        /* Weasyprint does not support JS, so Mermaid diagrams will appear as code blocks. This is expected. */
        pre.mermaid {{ background-color: #f0f8ff; border-left: 5px solid #add8e6; }}
    </style>
</head>
<body>
    {html_content}
</body>
</html>"""
    return full_html_doc, latex_formulas


async def display_lec_all_path(message: Message, repo_path: str, path: str, is_edit: bool = False):
    """Helper to fetch and display contents of a path in the lec_all repo."""
    status_msg = None
    if is_edit:
        # The callback is already answered, so we just edit the text.
        pass
    else:
        status_msg = await message.answer(f"Загружаю содержимое `/{path or 'корня'}` из `{repo_path}`...", parse_mode='markdown')

    contents = await github_service.get_github_repo_contents(repo_path, path)

    if contents is None:
        error_text = "Не удалось получить содержимое репозитория. Возможно, проблема с токеном GitHub или API."
        if status_msg:
            await status_msg.edit_text(error_text)
        elif is_edit:
            await message.edit_text(error_text, reply_markup=None)
        else:
            await message.answer(error_text)
        return

    builder = InlineKeyboardBuilder()

    # Add a "back" button if not in the root directory
    if path:
        # The full path for navigation now includes the repo
        parent_dir = path.rsplit('/', 1) if '/' in path else ""
        parent_path = f"{repo_path}/{parent_dir}" if parent_dir else repo_path
        path_hash = hashlib.sha1(parent_path.encode()).hexdigest()[:16]
        kb.code_path_cache[path_hash] = parent_path
        builder.row(InlineKeyboardButton(text="⬅️ .. (Назад)", callback_data=f"abs_nav_hash:{path_hash}"))

    if not contents:
        # The directory is empty, but we still want to show the back button if applicable.
        pass
    elif isinstance(contents, list):
        for item in contents:
            if item['type'] == 'dir':
                full_item_path = f"{repo_path}/{item['path']}"
                path_hash = hashlib.sha1(full_item_path.encode()).hexdigest()[:16]
                kb.code_path_cache[path_hash] = full_item_path
                builder.row(InlineKeyboardButton(
                    text=f"📁 {item['name']}",
                    callback_data=f"abs_nav_hash:{path_hash}"
                ))
            elif item['type'] == 'file':
                full_item_path = f"{repo_path}/{item['path']}"
                path_hash = hashlib.sha1(full_item_path.encode()).hexdigest()[:16]
                kb.code_path_cache[path_hash] = full_item_path
                builder.row(InlineKeyboardButton(
                    text=f"📄 {item['name']}",
                    callback_data=f"abs_show_hash:{path_hash}"
                ))
    
    message_text = f"Содержимое: `/{path}` в `{repo_path}`" if path else f"Содержимое `{repo_path}`"
    
    if not contents and not path: # Root is empty
        message_text = "Репозиторий пуст."
    elif not contents and path: # Sub-directory is empty
        message_text = f"Папка `/{path}` пуста."

    reply_markup = builder.as_markup() if builder.buttons else None

    if is_edit:
        try:
            await message.edit_text(message_text, reply_markup=reply_markup, parse_mode='markdown')
        except TelegramBadRequest as e:
            if "message is not modified" not in e.message:
                raise
    elif status_msg:
        await status_msg.edit_text(message_text, reply_markup=reply_markup, parse_mode='markdown')
    else:
        await message.answer(message_text, reply_markup=reply_markup, parse_mode='markdown')

async def show_code_by_path(message: Message, user_id: int, code_path: str, header: str):
    """Helper function to send code to the user based on its path."""
    try:
        submodule, topic, code_name = code_path.split('.')
        
        module = matplobblib._importlib.import_module(f'matplobblib.{submodule}')

        # Определяем, показывать ли docstring, на основе настроек пользователя
        settings = await database.get_user_settings(user_id)
        dict_name = 'themes_list_dicts_full' if settings['show_docstring'] else 'themes_list_dicts_full_nd'
        code_dictionary = getattr(module, dict_name)

        repl = code_dictionary[topic][code_name]

        await message.answer(f'{header}: \n{code_path.replace(".", " -> ")}')
        
        if len(repl) > 4096:
            await message.answer('Сообщение будет отправлено в нескольких частях')
            for x in range(0, len(repl), 4096):
                await message.answer(f'''```python\n{repl[x:x+4096]}\n```''', parse_mode='markdown')
        else:
            await message.answer(f'''```python\n{repl}\n```''', parse_mode='markdown')
        
        await message.answer("Что делаем дальше?", reply_markup=kb.get_code_action_keyboard(code_path))
        await message.answer("Или выберите другую команду.", reply_markup=kb.get_main_reply_keyboard(user_id))

    except (ValueError, KeyError, AttributeError, ImportError) as e:
        logging.error(f"Ошибка при показе кода (path: {code_path}): {e}")
        await message.answer("Не удалось найти или отобразить этот пример кода. Возможно, он был удален или перемещен.")
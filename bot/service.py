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
from aiogram.types import Message, CallbackQuery, FSInputFile, BufferedInputFile, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder
import markdown
from markdown_it import MarkdownIt
from pathlib import Path
import aiodocker
from aiodocker.exceptions import DockerError
import stat

from . import database
import matplobblib
from . import keyboards as kb
from . import github_service
from .config import *


logger = logging.getLogger(__name__)

RUNNER_IMAGE_NAME = "mpb-runner"
EXECUTION_TIMEOUT = 15
SHARED_DIR_INSIDE_BOT = "/app/code"
SHARED_VOLUME_NAME = "code_runner_data"

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
    
    # --- 
    # NOTE: pmatrix->array conversion is handled by pandoc_math_filter.lua
    # (we skip the Python-level regex to avoid double-conversion that corrupts math).

    # Heuristic fix for pmatrix environments containing \hline.
    # The pmatrix environment does not support \hline, causing a compilation error.
    # This fix replaces the pmatrix with a functionally equivalent array environment
    # which does support \hline.
    # processed_latex = re.sub(
    #     r'\\begin{pmatrix}(.*?)\\end{pmatrix}', 
    #     _pmatrix_hline_fixer, 
    #     processed_latex, 
    #     flags=re.DOTALL
    # )
    # --- 

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
                mmdc_path, '-p', str(PUPPETEER_CONFIG_PATH),
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

def _pmatrix_hline_fixer(match: re.Match) -> str:
    """Callback-функция для исправления \hline внутри pmatrix."""
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

# service.py

# ... (импорты и другие функции, включая _pmatrix_hline_fixer) ...

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

async def _resolve_wikilinks(content: str, repo_path: str, all_repo_files: list[str], target_format: str = 'md') -> str:
    """
    Находит все [[wikilinks]] и заменяет их стандартными Markdown-ссылками.
    Эта версия избегает обработки ссылок внутри математических окружений LaTeX.
    Она *всегда* выводит Markdown-ссылки, позволяя Pandoc корректно выполнять
    финальную конвертацию в LaTeX или HTML, что является более надежным подходом.
    """
    if not all_repo_files or '[[' not in content:
        return content

    # Создаем карту для быстрого поиска файлов по их "вики-именам"
    file_map = {os.path.splitext(os.path.basename(f))[0].lower(): f for f in all_repo_files}

    def replace_wikilink(match):
        inner_content = match.group(1).strip()
        parts = inner_content.split('|', 1)
        file_name_part = parts[0].strip()
        display_text = parts[1].strip() if len(parts) > 1 else file_name_part
        found_path = file_map.get(file_name_part.lower())

        if found_path:
            # Создаем полную URL-ссылку на файл в GitHub
            url = f"https://github.com/{repo_path}/blob/{github_service.MD_SEARCH_BRANCH}/{quote(found_path)}"
            
            # --- ВСЕГДА ВОЗВРАЩАЕМ СТАНДАРТНУЮ MARKDOWN-ССЫЛКУ ---
            # Pandoc сам корректно преобразует [текст](url) в \href{url}{текст}
            # и экранирует спецсимволы. Разделение на 'md' и 'latex' здесь не нужно.
            return f"[{display_text}]({url})"
        else:
            # Если файл не найден, просто возвращаем текст
            return f"_{display_text}_"

    # Регулярное выражение для поиска [[wikilinks]]
    wikilink_regex = r"\[\[([^\]]+)\]\]"

    # Регулярное выражение для захвата математических блоков LaTeX, чтобы их не трогать
    math_env_regex = r'(\$\$.*?\$\$|\$[^$\n]*?\$|\\\[.*?\\\]|\\\(.*?\\\)|\\begin\{(?:equation|align|gather|math|displaymath|matrix|pmatrix|array)[\*]?\}.*?\\end\{(?:equation|align|gather|math|displaymath|matrix|pmatrix|array)[\*]?\})'
    
    # Разбиваем контент на математические и текстовые части
    parts = re.split(math_env_regex, content, flags=re.DOTALL)

    processed_parts = []
    for i, part in enumerate(parts):
        # Четные элементы - это обычный текст, в них ищем и заменяем ссылки
        if i % 2 == 0:
            processed_parts.append(re.sub(wikilink_regex, replace_wikilink, part))
        # Нечетные элементы - это математика, оставляем их без изменений
        else:
            processed_parts.append(part)

    # Собираем все части обратно в одну строку
    return "".join(processed_parts)

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
        
        await message.bot.send_chat_action(message.chat.id, "upload_document") 
        
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
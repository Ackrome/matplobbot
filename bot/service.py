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
import aiohttp
from PIL import Image
from telegraph.aio import Telegraph
from telegraph.exceptions import TelegraphException
from aiogram.types import Message, CallbackQuery, FSInputFile, BufferedInputFile, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder
import markdown

from . import database
import matplobblib
from . import keyboards as kb

logger = logging.getLogger(__name__)

# --- Constants ---
LATEX_PREAMBLE = r"""
\documentclass[12pt,varwidth=500pt]{standalone}
\usepackage[utf8]{inputenc}
\usepackage[T2A]{fontenc}
\usepackage[russian]{babel}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{amsfonts}
\usepackage{graphicx}
\usepackage{color}
\usepackage{mhchem}
\usepackage{xcolor}
\begin{document}
"""
LATEX_POSTAMBLE = r"\end{document}"
MD_SEARCH_REPO = "kvdep/Abstracts"
MD_SEARCH_BRANCH = "main"

# --- Telegraph Client ---
telegraph_client = None

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
def _render_latex_sync(latex_string: str, padding: int, is_display_override: bool | None = None) -> io.BytesIO:
    """Синхронная функция для рендеринга LaTeX в PNG с использованием latex и dvipng, с добавлением отступов."""
    
    # Для команды /latex по умолчанию считаем формулу блочной (display) для лучшего качества.
    # Для обработки markdown флаг передается явно.
    is_display = is_display_override if is_display_override is not None else True

    # Удаляем переносы строк, заменяя их пробелами, чтобы избежать ошибок компиляции.
    processed_latex = latex_string.replace('\n', ' ').strip()
    s = processed_latex

    # Список окружений, которые сами создают математический режим.
    # Окружения типа 'cases', 'pmatrix' и т.д. в этот список не входят,
    # так как они должны находиться внутри математического режима.
    standalone_math_envs = [
        'equation', 'equation*',
        'align', 'align*',
        'gather', 'gather*',
        'multline', 'multline*',
        'displaymath', 'math',
        'alignat', 'alignat*',
        'flalign', 'flalign*'
    ]
    # Проверяем, начинается ли строка с \begin{...}, где ... - одно из автономных окружений.
    starts_with_standalone_env = False
    match = re.match(r'\\begin\{([a-zA-Z\*]+)\}', s)
    if match and match.group(1) in standalone_math_envs:
        starts_with_standalone_env = True

    is_already_math_env = (
        (s.startswith('$') and s.endswith('$')) or
        (s.startswith('$$') and s.endswith('$$')) or
        (s.startswith(r'\[') and s.endswith(r'\]')) or
        starts_with_standalone_env
    )

    if is_display_override is None:
        # Logic for /latex command: auto-detect and wrap if needed
        if not is_already_math_env:
            processed_latex = f'${processed_latex}$'
    else:
        # Logic for markdown processing: we know it's math, just wrap it correctly.
        if not is_already_math_env:
            # Using \[...\] for display is better than $$...$$
            if is_display_override:
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
                    # Поиск конкретной строки с ошибкой
                    error_lines = [line for line in log_content.split('\n') if line.startswith('! ')]
                    if error_lines:
                        error_message = error_lines[0].strip()
                    else: # Если '!' не найдено, показываем конец лога
                        error_message = "...\n" + "\n".join(log_content.split('\n')[-20:])
            raise ValueError(f"Ошибка компиляции LaTeX:\n{error_message}")

        # --- Запуск dvipng для конвертации DVI в PNG ---
        # Возвращаем постоянный DPI для всех формул для консистентности.
        dpi = 300
        dvipng_process = subprocess.run(
            ['dvipng', '-D', str(dpi), '-T', 'tight', '-bg', 'Transparent', '-o', png_path, dvi_path],
            capture_output=True, text=True, encoding='utf-8', errors='ignore'
        )
        
        if dvipng_process.returncode != 0 or not os.path.exists(png_path):
            raise RuntimeError(f"Ошибка dvipng: {dvipng_process.stderr}")

        # --- Добавление отступов и выравнивание с помощью Pillow ---
        with Image.open(png_path) as img:
            if is_display:
                # Для блочных формул создаем изображение фиксированной ширины и центрируем формулу.
                # Это обеспечивает визуальное выравнивание всех блочных формул в статье.
                target_width = 600  # Ширина в пикселях, подходящая для Telegra.ph
                
                # Если исходное изображение с отступами шире, мы его не обрезаем, а используем его ширину.
                # Это предотвращает потерю данных для очень широких формул.
                final_width = max(img.width + 2 * padding, target_width)
                final_height = img.height + 2 * padding
                
                new_img = Image.new("RGBA", (final_width, final_height), (0, 0, 0, 0))
                
                # Рассчитываем позицию для вставки, чтобы отцентрировать изображение
                paste_x = (final_width - img.width) // 2
                paste_y = padding
                
                new_img.paste(img, (paste_x, paste_y))
            else:
                # Для строчных формул просто добавляем отступы, чтобы они оставались компактными.
                final_width = img.width + 2 * padding
                final_height = img.height + 2 * padding
                new_img = Image.new("RGBA", (final_width, final_height), (0, 0, 0, 0))
                new_img.paste(img, (padding, padding))

            # Сохраняем результат в буфер в памяти
            buf = io.BytesIO()
            new_img.save(buf, format='PNG')
            buf.seek(0)
            return buf

async def render_latex_to_image(latex_string: str, padding: int, is_display_override: bool | None = None) -> io.BytesIO:
    """Асинхронная обертка для рендеринга LaTeX, выполняемая в отдельном потоке."""
    return await asyncio.to_thread(_render_latex_sync, latex_string, padding, is_display_override)

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

# --- Markdown and Abstracts ---
def preprocess_html_for_telegraph(html_content: str) -> str:
    """Replaces unsupported HTML tags with tags supported by Telegra.ph."""
    # h1, h2 -> h3, h4
    html_content = html_content.replace('<h1>', '<h3>').replace('</h1>', '</h3>')
    html_content = html_content.replace('<h2>', '<h4>').replace('</h2>', '</h4>')
    # h5, h6 -> bold paragraph
    html_content = html_content.replace('<h5>', '<p><b>').replace('</h5>', '</b></p>')
    html_content = html_content.replace('<h6>', '<p><b>').replace('</h6>', '</b></p>')

    # Crude table removal to prevent errors, replacing with a placeholder.
    import re
    html_content = re.sub(
        r'<table.*?>.*?</table>', 
        '<p><i>[Таблица была удалена, так как не поддерживается Telegra.ph]</i></p>', 
        html_content, 
        flags=re.DOTALL
    )
    
    return html_content

async def get_telegraph_client() -> Telegraph | None:
    """Initializes and returns an async Telegraph client instance. Creates a new account if no token is provided."""
    global telegraph_client
    if telegraph_client:
        return telegraph_client

    token = os.getenv("TELEGRAPH_TOKEN")
    client = Telegraph(access_token=token)

    if not token:
        try:
            await client.create_account(short_name='Matplobbot', author_name='Matplobbot', author_url='https://github.com/Ackrome/matplobbot')
            new_token = client.access_token
            logger.info(f"Created new Telegraph account. Your TELEGRAPH_TOKEN is: {new_token}. Please set it as an environment variable to reuse the account.")
            telegraph_client = client
        except Exception as e:
            logger.error(f"Could not create Telegraph account: {e}", exc_info=True)
            return None
    else:
        try:
            await client.get_account_info()
            logger.info("Telegraph client initialized with existing token.")
            telegraph_client = client
        except TelegraphException as e:
            logger.error(f"Telegraph token is invalid: {e}. Please check your TELEGRAPH_TOKEN environment variable.", exc_info=True)
            return None

    return telegraph_client



# service.py

async def upload_image_to_telegraph(image_bytes: io.BytesIO, session: aiohttp.ClientSession) -> str | None:
    """Uploads an image to a GitHub repository and returns the raw content URL."""
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        logger.error("GITHUB_TOKEN environment variable not set. Image upload to GitHub is disabled.")
        return None

    image_bytes.seek(0)
    image_data = image_bytes.read()
    
    if not image_data:
        logger.warning("Attempted to upload an empty image.")
        return None

    # Create a unique filename based on the content hash
    image_hash = hashlib.sha1(image_data).hexdigest()
    filename = f"{image_hash}.png"
    
    # Define repository details
    repo_owner = "Ackrome"
    repo_name = "matplobbot"
    repo_path = f"image/latex_render/{filename}"
    branch = "main"

    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{repo_path}"
    raw_url = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/{branch}/{repo_path}"

    # Base64 encode the image data for the GitHub API
    base64_content = base64.b64encode(image_data).decode('utf-8')

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    payload = {
        "message": f"feat: Add LaTeX render for {filename}",
        "content": base64_content,
        "branch": branch
    }

    try:
        async with session.put(api_url, headers=headers, json=payload) as response:
            if response.status == 201: # 201 Created
                response_data = await response.json()
                logger.info(f"Successfully uploaded image to GitHub: {response_data.get('content', {}).get('html_url')}")
                return response_data.get('content', {}).get('download_url', raw_url) # Return download_url, fallback to constructed raw_url
            elif response.status in [409, 422]: # 409 Conflict or 422 Unprocessable (file exists)
                logger.warning(f"Image {filename} already exists on GitHub. Returning existing URL.")
                return raw_url
            else:
                error_text = await response.text()
                logger.error(f"GitHub image upload API failed for {filename} with status {response.status}: {error_text}")
                return None
    except Exception as e:
        logger.error(f"Error during GitHub image upload request for {filename}: {e}", exc_info=True)
        return None

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

async def display_github_file(callback: CallbackQuery, file_path: str):
    """
    Fetches a file from GitHub and displays it, using Telegra.ph for Markdown files."""
    await callback.answer("Загружаю и обрабатываю файл...")
    raw_url = f"https://raw.githubusercontent.com/{MD_SEARCH_REPO}/{MD_SEARCH_BRANCH}/{file_path}"
    
    content = None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(raw_url) as response:
                if response.status == 200:
                    content = await response.text(encoding='utf-8', errors='ignore')
                else:
                    await callback.message.answer(f"Не удалось загрузить файл. Ошибка: {response.status}")
                    return
    except Exception as e:
        await callback.message.answer(f"Произошла ошибка при загрузке файла: {e}")
        return

    if content is None: # Check for None specifically
        await callback.message.answer("Не удалось получить содержимое файла.")
        return

    # Check if it's a markdown file
    if file_path.lower().endswith('.md'):
        try: # --- New Robust LaTeX + Markdown Processing ---

            # 1. Find all LaTeX formulas, replace with placeholders, and store them.
            latex_formulas = []

            def store_latex_match(match):
                # group(1) is for display mode $$...$$, group(2) is for inline mode $...$
                is_display = match.group(1) is not None
                code = match.group(1) if is_display else match.group(2)
                
                if code is not None:
                    # Используем уникальный кастомный тег в качестве заполнителя.
                    # Markdown-парсер его проигнорирует и оставит в итоговом HTML,
                    # в отличие от HTML-комментария, который он удаляет.
                    placeholder = f'<latex-placeholder id="{len(latex_formulas)}"></latex-placeholder>'
                    latex_formulas.append({
                        'code': code.strip(),
                        'is_display': is_display,
                        'placeholder': placeholder,
                        'original': match.group(0) # For fallback
                    })
                    return placeholder
                return match.group(0)

            # Regex to find $$...$$ (group 1) or $...$ (group 2).
            # The negative lookarounds for inline math prevent matching single dollars or parts of display math.
            latex_regex = r'\$\$(.*?)\$\$|(?<!\$)\$([^$]+?)\$(?!\$)'
            content_with_placeholders = re.sub(latex_regex, store_latex_match, content, flags=re.DOTALL)

            # 2. Convert the Markdown (with placeholders) to HTML.
            
            html_with_placeholders = markdown.markdown(
                content_with_placeholders, 
                extensions=['fenced_code', 'tables']
            )

            # 3. Asynchronously render all stored formulas to images and upload them.
            settings = await database.get_user_settings(callback.from_user.id)
            padding = settings['latex_padding']

            # Create one session for all uploads to improve efficiency and potentially avoid rate-limiting.
            async with aiohttp.ClientSession() as session:
                debug_photo_sent = True
                
                async def render_and_upload(formula_data):
                    nonlocal debug_photo_sent
                    try:
                        if not formula_data['code']: return None # Skip empty formulas
                        current_padding = padding if formula_data['is_display'] else max(0, padding - 10)
                        image_buffer = await render_latex_to_image(
                            formula_data['code'], 
                            current_padding, 
                            is_display_override=formula_data['is_display']
                        )
                        # --- НАЧАЛО ДИАГНОСТИЧЕСКОГО БЛОКА ---
                        if not debug_photo_sent:
                            try:
                                image_bytes = image_buffer.getvalue()
                                file_size = len(image_bytes)
                                
                                await callback.message.answer(
                                    f"🩺 **Диагностика:**\n"
                                    f"Первая сгенерированная картинка.\n"
                                    f"Размер: **{file_size} байт**.",
                                    parse_mode='markdown'
                                )

                                if file_size > 0:
                                    # Создаем копию для отправки, чтобы не повредить основной буфер
                                    debug_buffer = io.BytesIO(image_bytes)
                                    await callback.message.answer_photo(
                                        photo=BufferedInputFile(debug_buffer.read(), filename="debug_formula.png")
                                    )
                                else:
                                    await callback.message.answer("⚠️ **Диагностика:** Размер картинки 0 байт. Проблема в рендеринге LaTeX.")
                                
                            except Exception as e:
                                await callback.message.answer(f"❌ **Диагностика:** Не удалось отправить картинку в чат. Ошибка: {e}")
                            finally:
                                debug_photo_sent = True # Поднимаем флаг, чтобы не спамить в чат
                        
                        image_buffer.seek(0) # Возвращаем курсор буфера в начало для основной загрузки
                        # --- КОНЕЦ ДИАГНОСТИЧЕСКОГО БЛОКА ---

                        return await upload_image_to_telegraph(image_buffer, session)
                    except Exception as e:
                        logger.warning(f"Failed to render/upload LaTeX ('{formula_data['code']}'): {e}")
                        return None

                # Using a semaphore to limit concurrent requests to avoid overwhelming the system.
                semaphore = asyncio.Semaphore(1) # Reduced to 1 to make uploads sequential and avoid rate-limiting
                async def guarded_render(formula_data):
                    async with semaphore:
                        return await render_and_upload(formula_data)

                tasks = [guarded_render(f) for f in latex_formulas]
                image_urls = await asyncio.gather(*tasks)

            # 4. Replace placeholders in the HTML with the final <img> tags or error messages.
            final_html = html_with_placeholders
            for i, formula_data in enumerate(latex_formulas):
                url = image_urls[i]
                if url:
                    replacement = f'<figure><img src="{url}"></figure>' if formula_data['is_display'] else f'<img src="{url}">'
                else:
                    replacement = f'<i>[Ошибка рендеринга LaTeX: {formula_data["original"]}]</i>'
                final_html = final_html.replace(formula_data['placeholder'], replacement)

            # 5. Preprocess the final HTML for Telegra.ph compatibility.
            final_html = preprocess_html_for_telegraph(final_html)

            # 6. Get Telegraph client and create the page.
            telegraph = await get_telegraph_client()
            if not telegraph:
                await callback.message.answer("Ошибка: сервис Telegraph недоступен. Отправляю как простой текст.")
                await send_as_plain_text(callback.message, file_path, content)
            else:
                page_title = file_path.split('/')[-1].replace('.md', '')
                try:
                    response = await telegraph.create_page(title=page_title, html_content=final_html, author_name="Matplobbot", author_url="https://github.com/Ackrome/matplobbot")
                    page_url = response['url']
                    await callback.message.answer(f"Конспект **{file_path}** опубликован в Telegra.ph:\n{page_url}", parse_mode='markdown', disable_web_page_preview=False)
                except TelegraphException as e:
                    logger.error(f"Failed to create Telegraph page for '{file_path}': {e}", exc_info=True)
                    await callback.message.answer(f"Не удалось создать Telegra.ph статью: {e}. Отправляю как простой текст.")
                    await send_as_plain_text(callback.message, file_path, content)
        except Exception as e:
            logger.error(f"Ошибка при обработке Markdown и LaTeX для Telegraph '{file_path}': {e}", exc_info=True)
            await send_as_plain_text(callback.message, file_path, content)
    else:
        # Not a markdown file, send as plain text
        await send_as_plain_text(callback.message, file_path, content)
    
    await callback.message.answer("Выберите следующую команду:", reply_markup=kb.get_main_reply_keyboard(callback.from_user.id))

async def get_github_repo_contents(path: str = "") -> list[dict] | None:
    """Fetches directory contents from the GitHub repository."""
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        logger.error("GITHUB_TOKEN environment variable not set. /abstracts command is disabled.")
        return None

    # The URL for the contents API
    url = f"https://api.github.com/repos/{MD_SEARCH_REPO}/contents/{path}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {github_token}"
    }
    params = {"ref": MD_SEARCH_BRANCH}

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    # Sort items: folders first, then files, all alphabetically
                    if isinstance(data, list):
                        data.sort(key=lambda x: (x['type'] != 'dir', x['name'].lower()))
                    return data
                else:
                    error_text = await response.text()
                    logger.error(f"GitHub API contents fetch failed for path '{path}' with status {response.status}: {error_text}")
                    return None
    except Exception as e:
        logger.error(f"Error during GitHub API contents request for path '{path}': {e}", exc_info=True)
        return None

async def display_abstracts_path(message: Message, path: str, is_edit: bool = False):
    """Helper to fetch and display contents of a path in the abstracts repo."""
    status_msg = None
    if is_edit:
        # The callback is already answered, so we just edit the text.
        pass
    else:
        status_msg = await message.answer(f"Загружаю содержимое `/{path or 'корня'}`...", parse_mode='markdown')

    contents = await get_github_repo_contents(path)

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
        parent_path = path.rsplit('/', 1)[0] if '/' in path else ""
        path_hash = hashlib.sha1(parent_path.encode()).hexdigest()[:16]
        kb.code_path_cache[path_hash] = parent_path
        builder.row(InlineKeyboardButton(text="⬅️ .. (Назад)", callback_data=f"abs_nav_hash:{path_hash}"))

    if not contents:
        # The directory is empty, but we still want to show the back button if applicable.
        pass
    elif isinstance(contents, list):
        for item in contents:
            if item['type'] == 'dir':
                path_hash = hashlib.sha1(item['path'].encode()).hexdigest()[:16]
                kb.code_path_cache[path_hash] = item['path']
                builder.row(InlineKeyboardButton(
                    text=f"📁 {item['name']}",
                    callback_data=f"abs_nav_hash:{path_hash}"
                ))
            elif item['type'] == 'file':
                path_hash = hashlib.sha1(item['path'].encode()).hexdigest()[:16]
                kb.code_path_cache[path_hash] = item['path']
                builder.row(InlineKeyboardButton(
                    text=f"📄 {item['name']}",
                    callback_data=f"abs_show_hash:{path_hash}"
                ))
    
    message_text = f"Содержимое: `/{path}`" if path else "Содержимое корневой папки"
    
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

# --- Code Display ---
async def show_code_by_path(message: Message, code_path: str, header: str):
    """Helper function to send code to the user based on its path."""
    try:
        submodule, topic, code_name = code_path.split('.')
        
        module = matplobblib._importlib.import_module(f'matplobblib.{submodule}')

        # Определяем, показывать ли docstring, на основе настроек пользователя
        settings = await database.get_user_settings(message.from_user.id)
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
        await message.answer("Или выберите другую команду.", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))

    except (ValueError, KeyError, AttributeError, ImportError) as e:
        logging.error(f"Ошибка при показе кода (path: {code_path}): {e}")
        await message.answer("Не удалось найти или отобразить этот пример кода. Возможно, он был удален или перемещен.")
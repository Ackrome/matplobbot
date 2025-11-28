import os
import re
import base64
import tempfile
import subprocess
import shutil
import html
from PIL import Image
from bs4 import BeautifulSoup
from markdown_it import MarkdownIt
import io
from .celery_app import app
# Импортируем константы напрямую
from .constants import LATEX_PREAMBLE, LATEX_POSTAMBLE

# Пути к конфигам для Mermaid/Pandoc (они копируются в Dockerfile.worker в /app/bot/...)
BASE_DIR = "/app/bot"
MERMAID_FILTER_PATH = os.path.join(BASE_DIR, "pandoc_mermaid_filter.py")
MATH_FILTER_PATH = os.path.join(BASE_DIR, "pandoc_math_filter.lua")
PUPPETEER_CONFIG_PATH = os.path.join(BASE_DIR, "puppeteer-config.json")
PANDOC_HEADER_PATH = os.path.join(BASE_DIR, "templates", "pandoc_header.tex")

# Читаем хедер для Pandoc (если файла нет, используем пустую строку, чтобы не падало)
PANDOC_HEADER_INCLUDES = ""
if os.path.exists(PANDOC_HEADER_PATH):
    with open(PANDOC_HEADER_PATH, 'r', encoding='utf-8') as f:
        PANDOC_HEADER_INCLUDES = f.read()

@app.task(bind=True, soft_time_limit=45, name='shared_lib.tasks.render_latex')
def render_latex(self, latex_string: str, padding: int, dpi: int, is_display: bool):
    try:
        # 1. Preprocessing
        processed_latex = latex_string.strip()
        # Fix common LaTeX user errors
        processed_latex = re.sub(r'(\\end\{([a-zA-Z\*]+)\})(\s*\\tag\{.*?\})', r'\3 \1', processed_latex, flags=re.DOTALL)
        processed_latex = re.sub(r'(\\end\{([a-zA-Z\*]+)\})(\s*\\atop\s*(\\text\{.*?\}))', r'\\ \4 \1', processed_latex, flags=re.DOTALL)
        
        if not re.search(r'\\begin\{[a-zA-Z\*]+\}.*?\\end\{[a-zA-Z\*]+\}', processed_latex, re.DOTALL):
            processed_latex = processed_latex.replace('\n', ' ')

        # Wrap in equations if needed
        s = processed_latex
        if r'\tag' in s: is_display = True
        
        # Check if already wrapped
        is_already_math_env = (s.startswith('$') or s.startswith(r'\['))
        
        if not is_already_math_env:
            if r'\tag' in s:
                processed_latex = f'\\begin{{equation*}}\n{processed_latex}\n\\end{{equation*}}'
            elif is_display:
                processed_latex = f'\\[{processed_latex}\\]'
            else:
                processed_latex = f'${processed_latex}$'

        # Combine with PREAMBLE (imported from constants)
        full_latex_code = LATEX_PREAMBLE + processed_latex + LATEX_POSTAMBLE

        # 2. Compilation
        with tempfile.TemporaryDirectory() as temp_dir:
            tex_path = os.path.join(temp_dir, 'formula.tex')
            dvi_path = os.path.join(temp_dir, 'formula.dvi')
            png_path = os.path.join(temp_dir, 'formula.png')

            with open(tex_path, 'w', encoding='utf-8') as f:
                f.write(full_latex_code)

            # Run LaTeX
            subprocess.run(['latex', '-interaction=nonstopmode', '-output-directory', temp_dir, tex_path], capture_output=True)
            
            if not os.path.exists(dvi_path):
                # Try to read log for error
                log_content = "Unknown LaTeX error"
                log_path = os.path.join(temp_dir, 'formula.log')
                if os.path.exists(log_path):
                    with open(log_path, 'r', errors='ignore') as f: log_content = f.read()
                return {"status": "error", "error": log_content[-300:]}

            # Run dvipng
            subprocess.run(['dvipng', '-D', str(dpi), '-T', 'tight', '-bg', 'Transparent', '-o', png_path, dvi_path], capture_output=True)

            if not os.path.exists(png_path):
                return {"status": "error", "error": "dvipng conversion failed"}

            # 3. Post-processing (Padding)
            with Image.open(png_path) as img:
                final_width = max(img.width + 2 * padding, 600 if is_display else img.width + 2*padding)
                final_height = img.height + 2 * padding
                new_img = Image.new("RGBA", (final_width, final_height), (0, 0, 0, 0))
                paste_x = (final_width - img.width) // 2 if is_display else padding
                new_img.paste(img, (paste_x, padding))

                buf = io.BytesIO()
                new_img.save(buf, format='PNG')
                img_str = base64.b64encode(buf.getvalue()).decode('utf-8')
                return {"status": "success", "image": img_str}

    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.task(bind=True, soft_time_limit=45, name='shared_lib.tasks.render_mermaid')
def render_mermaid(self, mermaid_code: str):
    MMDC_PATH = shutil.which('mmdc') or 'mmdc'
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = os.path.join(temp_dir, 'diagram.mmd')
            output_path = os.path.join(temp_dir, 'diagram.png')
            
            with open(input_path, 'w', encoding='utf-8') as f:
                f.write(mermaid_code)
                
            command = [MMDC_PATH, '-p', PUPPETEER_CONFIG_PATH, '-i', input_path, '-o', output_path, '-b', 'transparent']
            process = subprocess.run(command, capture_output=True, text=True, errors='ignore')
            
            if process.returncode != 0 or not os.path.exists(output_path):
                err = process.stderr or "Unknown Error"
                return {"status": "error", "error": err.strip()}
                
            with open(output_path, 'rb') as f:
                img_str = base64.b64encode(f.read()).decode('utf-8')
                return {"status": "success", "image": img_str}
    except Exception as e:
        return {"status": "error", "error": str(e)}



def _pmatrix_hline_fixer(match: re.Match) -> str:
    """Helper for PDF pre-processing"""
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
        col_spec = 'c' * num_cols
        return f'\\left(\\begin{{array}}{{{col_spec}}}{matrix_content}\\end{{array}}\\right)'
    return match.group(0)

@app.task(bind=True, soft_time_limit=120, name='shared_lib.tasks.render_pdf')
def render_pdf_task(self, markdown_string: str, title: str, author_string: str, date_string: str):
    """
    Renders Markdown to PDF using Pandoc.
    Returns: {"status": "success", "pdf": base64_string}
    """
    try:
        # 1. Preprocessing (Logic from document_renderer.py)
        markdown_string = re.sub(r'(\\end\{([a-zA-Z\*]+)\})(\s*\\tag\{.*?\})', r'\3 \1', markdown_string, flags=re.DOTALL)
        markdown_string = re.sub(r'(\\end\{([a-zA-Z\*]+)\})(\s*\\atop\s*(\\text\{.*?\}))', r'\\ \4 \1', markdown_string, flags=re.DOTALL)
        
        def fix_starred_env_with_tag(match):
            env_name = match.group(1)
            content = match.group(2)
            if r'\tag' in content:
                return f"\\begin{{{env_name}}}{content}\\end{{{env_name}}}"
            return match.group(0)

        markdown_string = re.sub(r'\\begin\{([a-zA-Z]+)\*\}(.*?)\\end\{\1\*\}', fix_starred_env_with_tag, markdown_string, flags=re.DOTALL)
        markdown_string = re.sub(r'\\begin{pmatrix}(.*?)\\end{pmatrix}', _pmatrix_hline_fixer, markdown_string, flags=re.DOTALL)

        # 2. Compilation
        with tempfile.TemporaryDirectory() as temp_dir:
            header_path = os.path.join(temp_dir, 'header.tex')
            with open(header_path, 'w', encoding='utf-8') as f:
                f.write(PANDOC_HEADER_INCLUDES)

            tex_path = os.path.join(temp_dir, 'document.tex')
            pdf_path = os.path.join(temp_dir, 'document.pdf')

            # Pandoc command
            pandoc_cmd = [
                'pandoc',
                '--filter', MERMAID_FILTER_PATH,
                '--lua-filter', MATH_FILTER_PATH,
                '--from=gfm-yaml_metadata_block+tex_math_dollars+raw_tex',
                '--to=latex',
                '--pdf-engine=xelatex', 
                '--include-in-header', header_path,
                '--variable', f'title={title}',
                '--variable', f'author={author_string}',
                '--variable', f'date={date_string}',
                '--variable', 'documentclass=article',
                '--variable', 'geometry:margin=2cm',
                '-o', tex_path
            ]
            if re.search(r'^# ', markdown_string, re.MULTILINE):
                pandoc_cmd.append('--toc')

            # Run Pandoc to generate .tex
            proc_pandoc = subprocess.run(pandoc_cmd, input=markdown_string.encode('utf-8'), capture_output=True)
            if proc_pandoc.returncode != 0:
                return {"status": "error", "error": f"Pandoc failed: {proc_pandoc.stderr.decode('utf-8', 'ignore')}"}

            if not os.path.exists(tex_path):
                return {"status": "error", "error": "Pandoc did not create .tex file"}

            # Fix specific LaTeX artifacts (like \[ ... \] around aligns)
            with open(tex_path, 'r', encoding='utf-8') as f:
                tex_content = f.read()
            
            math_envs = r'(?:align|gather|equation|multline)'
            pattern = re.compile(r'\\\[\s*(\\begin\{' + math_envs + r'\*?\}.*?\\end\{' + math_envs + r'\*?\})\s*\\\]', re.DOTALL)
            tex_content_fixed = pattern.sub(r'\1', tex_content)
            
            with open(tex_path, 'w', encoding='utf-8') as f:
                f.write(tex_content_fixed)

            # Compile PDF with latexmk
            compile_cmd = [
                'latexmk', '-file-line-error', '-pdf', '-xelatex', '-interaction=nonstopmode',
                f'-output-directory={temp_dir}', tex_path
            ]
            proc_latex = subprocess.run(compile_cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')

            if not os.path.exists(pdf_path) or proc_latex.returncode != 0:
                log_file = os.path.join(temp_dir, 'document.log')
                log_content = ""
                if os.path.exists(log_file):
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        log_content = f.read()[-1000:]
                return {"status": "error", "error": f"LaTeX compilation failed. Log tail:\n{log_content}"}

            with open(pdf_path, 'rb') as f:
                pdf_b64 = base64.b64encode(f.read()).decode('utf-8')
                return {"status": "success", "pdf": pdf_b64}

    except Exception as e:
        return {"status": "error", "error": str(e)}

# --- HTML Task ---

@app.task(bind=True, soft_time_limit=30, name='shared_lib.tasks.render_html')
def render_html_task(self, content: str, page_title: str):
    """
    Renders Markdown to HTML string with KaTeX and TOC.
    Returns: {"status": "success", "html": html_string}
    """
    try:
        # 1. Isolate LaTeX
        latex_formulas = []
        def store_and_replace_latex(match):
            placeholder = f"<!--KATEX_PLACEHOLDER_{len(latex_formulas)}-->"
            latex_formulas.append(match.group(0))
            return placeholder

        latex_regex = r'(\$\$.*?\$\$|\$[^$\n]*?\$)'
        content_with_placeholders = re.sub(latex_regex, store_and_replace_latex, content, flags=re.DOTALL)

        # 2. Render Markdown
        md = MarkdownIt("commonmark", {"html": True, "linkify": True, "typographer": True}).enable('table')
        html_content = md.render(content_with_placeholders)

        # 3. Generate TOC and IDs
        soup = BeautifulSoup(html_content, 'html.parser')
        headings = soup.find_all(['h1', 'h2', 'h3'])
        toc_items = []
        used_ids = set()

        for heading in headings:
            text = heading.get_text()
            slug_base = re.sub(r'[^\w\s-]', '', text.lower()).strip().replace(' ', '-')
            slug = slug_base
            counter = 1
            while slug in used_ids:
                slug = f"{slug_base}-{counter}"
                counter += 1
            
            used_ids.add(slug)
            heading['id'] = slug
            level = int(heading.name[1])
            toc_items.append({'level': level, 'text': text, 'id': slug})

        toc_html = '<nav class="toc"><h4>Содержание</h4><ul>'
        for item in toc_items:
            toc_html += f'<li class="toc-level-{item["level"]}"><a href="#{item["id"]}">{item["text"]}</a></li>'
        toc_html += '</ul></nav>'

        html_content_with_ids = str(soup)

        # 4. Restore LaTeX
        processed_formulas = []
        for formula_string in latex_formulas:
            is_display = formula_string.startswith('$$')
            content_start, content_end = (2, -2) if is_display else (1, -1)
            original_content = formula_string[content_start:content_end].strip()

            if is_display and ('\n' in original_content or r'\atop' in original_content):
                temp_content = original_content.replace(r'\atop', r'\\')
                original_content = f"\\begin{{gathered}}\n{temp_content}\n\\end{{gathered}}"

            # Protect text blocks in LaTeX
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
            processed_formulas.append(f'$${final_content}$$' if is_display else f'${final_content}$')

        final_html_content = html_content_with_ids
        for i, formula in enumerate(processed_formulas):
            placeholder = f"<!--KATEX_PLACEHOLDER_{i}-->"
            final_html_content = final_html_content.replace(placeholder, formula)

        # 5. Final Templating
        final_html_content = final_html_content.replace(
            '<pre><code class="language-mermaid">', '<pre class="mermaid">'
        ).replace('</code></pre>', '</pre>')

        # (Здесь вставляется полный HTML шаблон, как в document_renderer.py, но я сокращу для примера)
        # На практике нужно скопировать переменную full_html_doc с CSS и JS скриптами.
        full_html_doc = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{page_title}</title>
    <!-- KATEX & MERMAID CDN LINKS & CSS HERE (COPY FROM ORIGINAL) -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css" crossorigin="anonymous">
    <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js" crossorigin="anonymous"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js" crossorigin="anonymous" onload="renderMathInElement(document.body);"></script>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
       /* CSS Styles from original file */
       body {{ font-family: sans-serif; padding: 20px; }}
       .toc {{ border: 1px solid #ccc; padding: 10px; margin-bottom: 20px; }}
    </style>
</head>
<body>
    {toc_html}
    <main>{final_html_content}</main>
    <script>
        document.addEventListener("DOMContentLoaded", function() {{
            if (typeof mermaid !== 'undefined') mermaid.initialize({{ startOnLoad: true }});
        }});
    </script>
</body>
</html>"""
        
        return {"status": "success", "html": full_html_doc}

    except Exception as e:
        return {"status": "error", "error": str(e)}
import os
import re
import base64
import tempfile
import subprocess
import shutil
import html
import io
import logging
from PIL import Image

from markdown_it import MarkdownIt
# texmath_plugin REMOVED to manually handle display math robustly
from mdit_py_plugins.anchors import anchors_plugin
from mdit_py_plugins.front_matter import front_matter_plugin

from .celery_app import app
from .constants import LATEX_PREAMBLE, LATEX_POSTAMBLE

logger = logging.getLogger(__name__)

# Пути к конфигам
BASE_DIR = "/app/bot"
MERMAID_FILTER_PATH = os.path.join(BASE_DIR, "pandoc_mermaid_filter.py")
MATH_FILTER_PATH = os.path.join(BASE_DIR, "pandoc_math_filter.lua")
PUPPETEER_CONFIG_PATH = os.path.join(BASE_DIR, "puppeteer-config.json")
PANDOC_HEADER_PATH = os.path.join(BASE_DIR, "templates", "pandoc_header.tex")

CSS_TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "report.css")
JS_TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "report.js")

# Читаем хедер для Pandoc
PANDOC_HEADER_INCLUDES = ""
if os.path.exists(PANDOC_HEADER_PATH):
    with open(PANDOC_HEADER_PATH, 'r', encoding='utf-8') as f:
        PANDOC_HEADER_INCLUDES = f.read()

# ... [Оставлен код для render_latex, render_mermaid, render_pdf_task без изменений] ...
# ВАЖНО: убедитесь, что функции render_latex, render_mermaid и render_pdf_task остались на месте.
# Они не меняются, поэтому я их свернул для краткости ответа.

@app.task(bind=True, soft_time_limit=45, name='shared_lib.tasks.render_latex')
def render_latex(self, latex_string: str, padding: int, dpi: int, is_display: bool):
    try:
        processed_latex = latex_string.strip()
        processed_latex = re.sub(r'(\\end\{([a-zA-Z\*]+)\})(\s*\\tag\{.*?\})', r'\3 \1', processed_latex, flags=re.DOTALL)
        
        is_already_math_env = (processed_latex.startswith('$') or 
                               processed_latex.startswith(r'\[') or 
                               r'\begin' in processed_latex)
        
        if not is_already_math_env:
            if r'\tag' in processed_latex:
                processed_latex = f'\\begin{{equation*}}\n{processed_latex}\n\\end{{equation*}}'
            elif is_display:
                processed_latex = f'\\[{processed_latex}\\]'
            else:
                processed_latex = f'${processed_latex}$'

        full_latex_code = LATEX_PREAMBLE + processed_latex + LATEX_POSTAMBLE

        with tempfile.TemporaryDirectory() as temp_dir:
            tex_path = os.path.join(temp_dir, 'formula.tex')
            dvi_path = os.path.join(temp_dir, 'formula.dvi')
            png_path = os.path.join(temp_dir, 'formula.png')

            with open(tex_path, 'w', encoding='utf-8') as f:
                f.write(full_latex_code)

            proc = subprocess.run(
                ['latex', '-interaction=nonstopmode', '-output-directory', temp_dir, tex_path],
                capture_output=True, timeout=30
            )
            
            if not os.path.exists(dvi_path):
                log_path = os.path.join(temp_dir, 'formula.log')
                error_msg = "Unknown LaTeX error"
                if os.path.exists(log_path):
                    with open(log_path, 'r', errors='ignore') as f:
                        log_lines = f.readlines()
                    errors = [line.strip() for line in log_lines if line.startswith('!')]
                    error_msg = "\n".join(errors[:3]) if errors else "\n".join(log_lines[-10:])
                return {"status": "error", "error": error_msg}

            subprocess.run(
                ['dvipng', '-D', str(dpi), '-T', 'tight', '-bg', 'Transparent', '-o', png_path, dvi_path],
                capture_output=True, timeout=10
            )

            if not os.path.exists(png_path):
                return {"status": "error", "error": "dvipng conversion failed"}

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

    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "Rendering timed out."}
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
            process = subprocess.run(command, capture_output=True, text=True, errors='ignore', timeout=30)
            
            if process.returncode != 0 or not os.path.exists(output_path):
                err = process.stderr or "Unknown Error"
                return {"status": "error", "error": err.strip()}
                
            with open(output_path, 'rb') as f:
                img_str = base64.b64encode(f.read()).decode('utf-8')
                return {"status": "success", "image": img_str}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.task(bind=True, soft_time_limit=120, name='shared_lib.tasks.render_pdf')
def render_pdf_task(self, markdown_string: str, title: str, author_string: str, date_string: str):
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            header_path = os.path.join(temp_dir, 'header.tex')
            with open(header_path, 'w', encoding='utf-8') as f:
                f.write(PANDOC_HEADER_INCLUDES)

            tex_path = os.path.join(temp_dir, 'document.tex')
            pdf_path = os.path.join(temp_dir, 'document.pdf')

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

            proc_pandoc = subprocess.run(pandoc_cmd, input=markdown_string.encode('utf-8'), capture_output=True, timeout=45)
            
            if proc_pandoc.returncode != 0:
                return {"status": "error", "error": f"Pandoc failed: {proc_pandoc.stderr.decode('utf-8', 'ignore')}"}

            compile_cmd = [
                'latexmk', '-pdf', '-xelatex', '-interaction=nonstopmode', '-halt-on-error',
                f'-output-directory={temp_dir}', tex_path
            ]
            
            proc_latex = subprocess.run(compile_cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=60)

            if not os.path.exists(pdf_path) or proc_latex.returncode != 0:
                log_file = os.path.join(temp_dir, 'document.log')
                log_content = ""
                if os.path.exists(log_file):
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                    error_lines = [l.strip() for l in lines if l.startswith('!')]
                    log_content = "\n".join(error_lines[:5]) if error_lines else "\n".join(lines[-20:])
                
                return {"status": "error", "error": f"LaTeX compilation failed:\n{log_content}"}

            with open(pdf_path, 'rb') as f:
                pdf_b64 = base64.b64encode(f.read()).decode('utf-8')
                return {"status": "success", "pdf": pdf_b64}

    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "Process timed out."}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def generate_toc_from_tokens(tokens) -> str:
    """
    Manually generates HTML TOC from markdown-it tokens.
    """
    toc_html = '<nav class="toc"><h4>Содержание</h4><ul>'
    for i in range(len(tokens)):
        if tokens[i].type == 'heading_open':
            tag = tokens[i].tag 
            level = int(tag[1])
            attrs = tokens[i].attrs or {}
            anchor_id = attrs.get('id', '')
            if i + 1 < len(tokens) and tokens[i+1].type == 'inline':
                text = tokens[i+1].content
                toc_html += f'<li class="toc-level-{level}"><a href="#{anchor_id}">{html.escape(text)}</a></li>'
    toc_html += '</ul></nav>'
    return toc_html

@app.task(bind=True, soft_time_limit=30, name='shared_lib.tasks.render_html')
def render_html_task(self, content: str, page_title: str):
    """
    Renders Markdown to HTML using markdown-it-py.
    Manual math protection ensures Obsidian compatibility for block math ($$).
    FIX: Changed placeholders to avoid Markdown parser interference (removed underscores).
    """
    try:
        # 1. Protect Math: Convert $$...$$ and $...$ to temporary placeholders.
        # FIX: We use 'PHMATHBLOCK{i}PH' instead of '__MATH_BLOCK_{i}__'
        # because markdown parsers often interpret '__' as bold text start/end.
        
        protected_math = []
        
        def protect_block(match):
            idx = len(protected_math)
            placeholder = f"PHMATHBLOCK{idx}PH"
            protected_math.append(match.group(0))
            return placeholder

        def protect_inline(match):
            idx = len(protected_math)
            placeholder = f"PHMATHINLINE{idx}PH"
            protected_math.append(match.group(0))
            return placeholder

        # Protect Block Math ($$ ... $$)
        content = re.sub(r'\$\$(.*?)\$\$', protect_block, content, flags=re.DOTALL)
        
        # Protect Inline Math ($ ... $)
        content = re.sub(r'\$([^$\n]+)\$', protect_inline, content)

        # 2. Initialize Parser without texmath
        md = (
            MarkdownIt("commonmark", {"html": True, "linkify": True, "typographer": True})
            .enable('table')
            .use(front_matter_plugin)
            # permalink=False removes the '¶' symbol
            .use(anchors_plugin, min_level=1, max_level=3, permalink=False)
        )

        # 3. Parse tokens & Generate TOC
        tokens = md.parse(content)
        toc_html = generate_toc_from_tokens(tokens)

        # 4. Render HTML
        html_body = md.renderer.render(tokens, md.options, {})

        # 5. Restore Math placeholders
        for i, math_code in enumerate(protected_math):
            if math_code.startswith('$$'):
                # Block Math Restoration
                # Wrap in .katex-display div to enforce block styling and centering via CSS
                replacement = f'<div class="katex-display">{html.escape(math_code)}</div>'
                html_body = html_body.replace(f"PHMATHBLOCK{i}PH", replacement)
            else:
                # Inline Math Restoration
                replacement = f'<span class="katex-inline">{html.escape(math_code)}</span>'
                html_body = html_body.replace(f"PHMATHINLINE{i}PH", replacement)

        # 6. Post-processing for Mermaid
        html_body = html_body.replace(
            '<pre><code class="language-mermaid">', '<pre class="mermaid">'
        ).replace('</code></pre>', '</pre>')

        # 7. Load Styles/Scripts
        css_content = ""
        js_content = ""
        if os.path.exists(CSS_TEMPLATE_PATH):
            with open(CSS_TEMPLATE_PATH, 'r', encoding='utf-8') as f: css_content = f.read()
        if os.path.exists(JS_TEMPLATE_PATH):
            with open(JS_TEMPLATE_PATH, 'r', encoding='utf-8') as f: js_content = f.read()

        full_html_doc = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(page_title)}</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css" crossorigin="anonymous">
    <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js" crossorigin="anonymous"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js" crossorigin="anonymous"></script>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>{css_content}</style>
</head>
<body>
    {toc_html}
    <main>{html_body}</main>
    <script>{js_content}</script>
</body>
</html>"""
        
        return {"status": "success", "html": full_html_doc}

    except Exception as e:
        return {"status": "error", "error": str(e)}
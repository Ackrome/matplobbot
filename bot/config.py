
from pathlib import Path
import os
BASE_DIR = Path(__file__).parent 

PANDOC_HEADER_PATH = BASE_DIR / "templates" / "pandoc_header.tex"
LATEX_PREAMBLE_PATH = BASE_DIR / "templates" / "latex_preamble.tex"
PUPPETEER_CONFIG_PATH = BASE_DIR / "puppeteer-config.json"
MERMAID_FILTER_PATH = BASE_DIR / "pandoc_mermaid_filter.py"
MATH_FILTER_PATH = BASE_DIR / "pandoc_math_filter.lua"

LATEX_POSTAMBLE = r"\end{document}"
MD_LATEX_PADDING = 15
SEARCH_RESULTS_PER_PAGE = 10
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID'))



with open(PANDOC_HEADER_PATH, 'r', encoding='utf-8') as f:
    PANDOC_HEADER_INCLUDES = f.read()
with open(LATEX_PREAMBLE_PATH, 'r', encoding='utf-8') as f:
    LATEX_PREAMBLE = f.read()
    


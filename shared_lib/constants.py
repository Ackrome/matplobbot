# shared_lib/constants.py

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
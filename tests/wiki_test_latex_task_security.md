# `test_latex_task_security.py`

## Purpose

Regression tests for LaTeX compilation security checks.

## Public tests

`TestLatexTaskSecurity` covers safe source, shell/file-I/O commands, absolute and traversal paths, binary LaTeX payloads, and rejection before `subprocess.run`.

## Usage

Run `python -m unittest tests.test_latex_task_security` from the project root.

## Dependencies and side effects

Uses `unittest` and `unittest.mock`; subprocess execution is patched, so tests do not compile TeX or modify files outside temporary task directories.

## Maintenance notes

Add a regression case whenever a new TeX input channel or compiler flag is introduced. Keep assertions focused on rejecting unsafe input before compilation starts.

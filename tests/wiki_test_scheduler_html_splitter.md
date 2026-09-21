# `test_scheduler_html_splitter.py`

## Purpose

Regression tests for balanced splitting of long Telegram HTML messages.

## Public tests

`TestSchedulerHTMLSplitter` checks empty and short messages, nested tags, code/pre blocks, and impossible size limits.

## Usage

Run `python -m unittest tests.test_scheduler_html_splitter` from the project root.

## Dependencies and side effects

Uses `unittest` and `shared_lib.html_tools`; no network or filesystem side effects occur.

## Maintenance notes

Keep test limits below the Telegram maximum when testing chunk mechanics, and add coverage for each newly supported HTML tag shape.

# Fixed field fusion regression checks

`test_curriculum_ocr_fusion.py` checks observable routing behavior without OCR
weights: paired valid-index fallback, preservation of the primary valid index,
numeric disagreement versus empty cells, missing source rejection, and input
immutability. Fixtures are synthetic, not discipline GT answers.

Run `./.venv/Scripts/python.exe -m unittest tests.test_curriculum_ocr_fusion`.
Dependencies are the stdlib and existing index/semester/benchmark modules. Tests
perform no network calls and write no files. Add regressions when routing changes,
but do not encode per-row corrections from a measured document in these tests.

# Surya adapter contract tests

`test_curriculum_ocr_surya.py` tests the optional offline Surya adapter without
Torch, downloaded models or a network server. It verifies that HTML table cells
remain separated, truncated output is preserved as evidence but abstains from
recognition, publisher prompt wording remains exact, and request limits are
bounded. `SuryaAdapterTests` uses an in-memory fake HTTP response and Pillow.

Run from the project root with `.venv/Scripts/python.exe -m unittest
tests.test_curriculum_ocr_surya`. No persistent side effects. Keep live quality
experiments outside CI; these contract tests do not measure OCR accuracy.

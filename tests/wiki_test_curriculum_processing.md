# test_curriculum_processing.py

Layout regressions reject unsupported values before spawning, exercise explicit
profile propagation through the real CLI, distinguish profile cache keys and
prevent native text-overlay records duplicating scan-row identities.

Regression tests for subprocess execution and text/OCR dispatch. `TestCurriculumWorker` exercises a real synthetic text-PDF child, environment and temporary-file cleanup, a real timeout/termination, parent cancellation, configuration bounds, parser/model cache keys and mixed-page dispatch (including a watermark on a scan).

Run `./.venv/Scripts/python.exe -m unittest tests.test_curriculum_processing -v`. Tests depend on existing PDF dependencies and synthetic fixtures from `test_curriculum_documents`; Tesseract is not required. The OCR parser call is mocked for mixed-page geometry selection while a real parser subprocess is used for text extraction.

Temporary files and processes are cleaned by the production runner. Timeout tests intentionally start a sleeping child and verify termination. Linux uses a process group and Windows uses `taskkill`; keep the platform branch exercised on the supported host. No network, production database or user data is used.

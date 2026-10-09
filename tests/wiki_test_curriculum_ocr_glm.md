# GLM table mapping tests

`test_curriculum_ocr_glm.py` checks blank-cell preservation, line breaks, merged
cells, truncated tables and strict geometric row/column counts. The public
`GlmTableMappingTests` unittest class uses synthetic HTML only and never downloads
models or starts a server. Run `.venv/Scripts/python.exe -m unittest
tests.test_curriculum_ocr_glm`. Keep these contracts aligned with positional
mapping: a structural mismatch must not silently shift assessment values.

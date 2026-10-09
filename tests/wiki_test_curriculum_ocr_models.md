# Optional OCR adapter contract tests

`test_curriculum_ocr_models.py` checks the numeric CTC decoder without network,
model downloads or Torch/ONNX model initialization. The tests preserve native
letters, retain the original probability of a constrained digit, keep blank
available, preserve CTC repeats and multi-digit section counts, reject invalid
probabilities, and reject GT-contaminated/path-traversing cell manifests.

Run `python -m unittest discover -s tests -p test_curriculum_ocr_models.py -v`
from the project root venv. Numeric tests require optional NumPy; manifest tests
also exercise the benchmark's optional OpenCV import. No production data changes.
Keep this suite focused on inference boundaries; accuracy comes from the separate
frozen scanned-plan benchmark rather than expected strings embedded in tests.

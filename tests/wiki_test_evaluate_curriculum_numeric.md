# Numeric evaluation boundary and metric tests

`test_evaluate_curriculum_numeric.py` checks strict counts for missing/abstained
blank cells, hallucinated controls, section totals, wrong names/kinds and extra
rows. Identical row IDs on different pages remain distinct; a wrong printed index
does not affect the requested physical-row/name assessment identity. Unrelated
horizontal geometry cannot match by text.

The suite rejects partial runs, nested GT labels in inference manifests, changed
weights and non-synthetic provenance. A mocked recognizer verifies all five blank
cells are passed through `read`, with no GT argument and no old blank-gate bypass.
It also checks that a previous complete result cannot mask a failed rerun.

Run `python -m unittest discover -s tests -p test_evaluate_curriculum_numeric.py -v`.
Most tests use only the standard library; one pixel-input test skips when optional
NumPy/OpenCV are unavailable. There are no model downloads, network calls, training
runs or production mutations. Maintain genuinely independent expected counts.

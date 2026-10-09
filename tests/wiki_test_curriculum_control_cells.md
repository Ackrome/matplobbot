# Numeric cell wrapping tests

`ControlWrappingTests` verifies geometric line separation and single-line
preservation, explicit separator recovery across line boundaries and abstention
when a line break would require inventing a comma. Fixtures use drawn digits and
an injected recognizer; no real document GT, model download or GPU is involved.

Run `.venv/Scripts/python.exe -m unittest tests.test_curriculum_control_cells`.
Dependencies: NumPy/OpenCV and unittest mocks. No persistent side effects.
Keep line-level syntax errors distinct from low-confidence recognition failures.
The failure-path test also prevents wrapping from rescuing low-confidence lines
or recognizer bounds/runtime failures despite an otherwise explicit separator.

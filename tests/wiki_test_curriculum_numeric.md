# Numeric CNN contract tests

`test_curriculum_numeric.py` verifies CTC repeat/blank semantics, empty cells
and border remnants, bounded grayscale inputs, and preservation of a compact
`123` without inventing semester separators. `NumericContractTests` uses synthetic
arrays and a fake inference session; no real curriculum GT or training model
is loaded. NumPy/OpenCV are optional and missing image dependencies skip tests.

Run `.venv/Scripts/python.exe -m unittest tests.test_curriculum_numeric` from the
project root. No downloads or persistent side effects. Live model accuracy and
CPU parity are evaluated separately on frozen exported weights.

# Native curriculum reference tests

`test_curriculum_vector_gt.py` verifies the independent PDF-text reference builder.
The cases distinguish the assessment header `Зачет` from `Зачетные единицы`,
recognize rotated and reordered native headers, reject ambiguous columns and
non-list semesters, and preserve physical rows/source typos in a synthetic
vector table. Parent section counts stay outside discipline semester labels.

Run `python -m unittest discover -s tests -p test_curriculum_vector_gt.py -v`.
The vector extraction test supplies a mocked pdfplumber document, so no real PDF,
OCR model, network, GPU or native PDF renderer is needed. It changes no production
data. Do not replace these independent fixtures with outputs from the recognizer
being evaluated; that would make the evaluation circular.

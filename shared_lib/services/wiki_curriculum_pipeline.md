# Names + numeric CNN curriculum pipeline

`curriculum_pipeline.py` renders PDF pages, deskews them, reconstructs ruled
tables and extracts assessment candidates. `parse_scanned_curriculum(content,
page_numbers=None, layout_profile=None)` is the production entry point through
`curriculum_ocr.parse_scanned_curriculum`. `parse_page` processes one page;
`clean_name` removes display-wrap whitespace and trailing line artifacts.

Example: `parse_scanned_curriculum(pdf_bytes, layout_profile="fa_legacy_v1")`.
Use the bounded scheduler worker in production, never an HTTP request process.
Dependencies: OpenCV, NumPy, pypdfium2; Tesseract rus+eng for exactly one name-column
batch per page; the packaged `NumericRecognizer` CNN and ONNX Runtime for the
five control columns. Headers, printed indices, departments and control values
are not sent to general OCR. There is no inference-time GT or expected-value
dictionary and no automatic fallback to the old all-OCR pipeline.

Column meanings come from a declared `curriculum_layout` template. Exact known
PDF hashes can select a previously verified template; a new revision needs its
persisted declaration. Geometry validates the declaration but cannot distinguish
different meanings in otherwise identical grids. Shaded section/total rows and
white rows lacking department ink are excluded structurally. The department's
content is never read. No assessment is inherited from a parent section.

Results retain all physical audit rows and typed abstentions. Candidate storage
uses `scan:p<page>:r<row>` as an internal, source-scoped identity in the existing
`discipline_code` field; this is explicitly not a recognized printed index.
`ocr.identity_method` and evidence make this provenance clear. Crops show the
deskewed source; bounding boxes are transformed back to normalized original PDF
coordinates. Duplicate printed indices therefore cannot merge different rows.

Side effects: bounded Tesseract subprocesses; transient PDF images and CPU model
memory. No network/model downloads or database writes. Eight-page, pixel, row,
time, output and crop limits are inherited from `curriculum_ocr`; failures discard
partial candidates. Existing publication/group binding remains separate from
automatic extraction. Tests must assert that only name crops reach general OCR,
that layout swaps fail, section counts never become semesters, unresolved cells
do not become empty successes, and original-page evidence survives deskew.

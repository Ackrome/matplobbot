# Pipeline regression tests

`test_curriculum_pipeline.py` checks declared layout selection/conflicts, damaged
grid rejection, structural section filtering, name-only general OCR, preservation
of multi-semester controls and source row identity, abstention/invalid sequences,
and original-page coordinates after deskew. `LayoutTests` and `PipelineTests`
use small synthetic rasters and injected numeric predictions; they do not claim
trained-model accuracy or require PDF/model downloads.

Run `.venv/Scripts/python.exe -m unittest tests.test_curriculum_pipeline`.
Dependencies: NumPy/OpenCV and existing geometry utilities. No network or persistent
writes. Keep the OCR spies: adding header/index/numeric text OCR to the runtime
must fail this contract. Actual model quality belongs to the frozen GT benchmark.

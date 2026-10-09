# Fixed field routing with paired numeric recognition

`curriculum_ocr_fusion.py` combines complete saved OCR results without reading GT.
It is an offline development policy, not a guarantee that an arbitrary document
is correct. Roles were chosen on the original 2023 audit before another document
was evaluated. All source hashes and physical row IDs must agree.

`fuse_predictions(names, codes, numeric_a, numeric_b)` selects names and indices
from fixed sources. An invalid primary index can use a fallback only when both
alternative recognizers produce the same valid canonical index. It never changes
an already valid primary index merely to agree with another model. Every numeric
control requires agreement in an unambiguous semester list, or identical literal
text for section counts. A disagreement remains explicit abstention. Raw text,
alternative readings and the reason for routing are preserved. Classification
of sections and discipline rows then uses the existing independent rules.

```powershell
./.venv/Scripts/python.exe scripts/curriculum_ocr_fusion.py `
  --names baseline.json --codes best_clean6.json `
  --numeric-a ppocr_v5_cyrillic__numeric.json `
  --numeric-b ppocr_v5_eslav__numeric.json --output fusion.json
```

Dependencies: the existing benchmark and curriculum index/semester parser;
there is no model initialization or external request. Only `--output` is written;
input predictions remain unchanged. The CLI deliberately has no GT argument.
Evaluate the result separately after saving it. Duplicate printed source indices
do not collapse physical rows. Missing rows, mismatched hashes and duplicate row
IDs reject fusion rather than silently omitting records. Model probabilities are
retained as evidence, not interpreted as calibrated cross-model confidence.

Changes to field priorities, acceptance rules or normalization require a version
bump and reevaluation on the frozen development and independent validation sets.

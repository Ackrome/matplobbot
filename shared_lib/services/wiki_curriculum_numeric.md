# Synthetic numeric CNN recognizer

`curriculum_numeric.py` recognizes complete numeric strings in already located
curriculum control cells. It has no discipline-name, index, header or document
classification API. The bundled CNN+CTC is trained exclusively on generated font
images; real curriculum annotations never enter its training inputs.

## API

```python
from shared_lib.services.curriculum_numeric import NumericRecognizer
recognizer = NumericRecognizer()  # packaged model + hash-checked JSON metadata
reading = recognizer.read(gray_uint8_cell)
if not reading['abstained']:
    print(reading['text'], reading['confidence'])
```

`read` returns text, original decoded `raw_text`, confidence on a 0–100 scale,
an abstention flag and reason, preprocessing diagnostics and the model hash.
An empty physical cell returns `reason=blank`; ambiguous recognition is explicit.
The alphabet is digits 0–9, comma and hyphen, with a separate CTC blank class.
`1,2,3` is a sequence. `123` stays `123`: semester interpretation belongs to the
caller and this module never inserts separators or infers assessment meaning.

`prepare_cell` handles grayscale contrast, narrow border remnants and bounded
aspect-preserving resizing. The identical function is used during synthesis.
`decode_ctc` collapses repeats while preserving equal digits separated by blanks.

## Dependencies and maintenance

Runtime requires NumPy, OpenCV and ONNX Runtime; imports are lazy. ORT explicitly
uses CPUExecutionProvider and one intra/inter-op thread. No Torch is imported
at inference. The default resources are `shared_lib/data/curriculum_numeric.onnx`
and matching JSON. The metadata hash, alphabet and synthetic-only provenance
are checked before loading; preserve both resources when packaging.

Image size, normalized width and model size are bounded. Low-confidence or
invalid sequences abstain. Confidence is a model score, not a guarantee of truth.
Do not tune the weights/threshold on the frozen real-table evaluation labels.
Use `scripts/train_curriculum_numeric.py` for reproducible synthetic training,
freeze model SHA before independent real-table evaluation, and retain the
generator/runtime source hashes and synthetic validation summary in metadata.
No network, database writes or automatic model downloads occur here.

# Wrapped numeric cells

`curriculum_control_cells.py` separates geometric line handling from the small
single-line CNN. `numeric_lines(gray)` finds foreground row bands, removes only
edge rules/specks and retains commas with their baseline. `read_control_cell(gray,
recognizer)` invokes the same CNN on each line and joins a sequence only when a
printed comma or range separator explicitly connects adjacent lines.

Example: images containing `1,2,` above `3,4` become `1,2,3,4`; `12` above `34`
remains unresolved rather than silently becoming either `1234` or `12,34`.
Line-level grammar rejections caused by a trailing separator may be recovered;
low-confidence or missing readings may not. Raw line readings are retained.

Dependencies: NumPy/OpenCV and a recognizer implementing `.read(gray)` plus
`threshold` (0–1) and `model_sha256`. No training, model mutation, GT lookup,
downloads or file writes. Images/line counts are bounded. Validate both raw
production crops and padded benchmark crops; false line splitting can corrupt
digits and must remain covered by synthetic single/multiline tests.

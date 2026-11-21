# Release evidence regression tests

`python -m unittest discover -s tests -p test_release_evidence.py` covers exact
workflow and artifact selection, ZIP checksum enforcement, redirects without
credential forwarding, schema-change dispatch and worker report identity,
inventory and report-only findings. Tests use synthetic artifacts and responses
and create files only in temporary directories. Keep fixtures aligned with the
pinned scanner's CycloneDX structure and deployment artifact contracts. These
fixtures do not replace a real GHCR scan or the disposable Docker compatibility
run in CI.

The versioned bundle cases also cover annotated tags, SHA and worker digest
binding, absence-only fallback, rejection of invalid published evidence and
idempotent publication without uploading a second copy.

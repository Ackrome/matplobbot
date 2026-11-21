# Audit the accepted worker image

`audit()` reads the validated deployed release evidence, runs Trivy for its
worker OCI digest on `linux/amd64` and verifies the resulting CycloneDX image
name, revision and scanner version. `inspect_bom()` requires explicit package
inventory for Debian Chromium, TeX Live and npm Mermaid. Trivy embeds
vulnerability findings in the CycloneDX document. Findings are report-only.

```sh
python3 scripts/worker_image_audit.py --baseline release-baseline.json \
  --scanner /path/to/verified/trivy --output-dir worker-image-audit
```

The CLI writes `worker-audit.json` for every run. Only a verified scan can write
`worker.cdx.json`. On a skip or error the directory contains the status instead
of a stale SBOM. The workflow pins the binary archive's SHA256, uses read-only
GHCR credentials and runs after deployment, weekly and manually from `main`.
Keep `SCANNER_VERSION`, the workflow archive checksum and fixture tests aligned
when changing the scanner. Update inventory checks if the worker's package
layout changes intentionally.

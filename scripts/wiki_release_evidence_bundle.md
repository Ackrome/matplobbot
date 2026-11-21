# Versioned release evidence bundles

`release_evidence_bundle.py` selects, packages and validates release evidence.
The bundle carries the accepted CI manifest, worker CycloneDX SBOM, audit summary
and a receipt linking the stable tag to the successful Actions deployment. The
tag is resolved to its full commit. The signer is restricted to the repository's
Worker Image Audit workflow on a GitHub-hosted runner, with a certificate claim
for the exact tag commit or the reviewed `main` workflow.

```sh
python3 scripts/release_evidence_bundle.py select --tag v1.2.0 --output release-baseline.json
python3 scripts/release_evidence_bundle.py pack --baseline release-baseline.json \
  --audit-directory worker-image-audit --output matplobbot-release-evidence.zip
```

`select --prefer-published` verifies the latest stable release's attachment before
giving its worker digest to the weekly scanner. Older releases without the asset
use the existing Actions deployment proof lookup. A checksum or signature error
does not trigger fallback. `publish` verifies an existing attachment and reuses it,
or checks the newly attested ZIP and attaches it to the matched release. It uses
the GitHub API via `GH_TOKEN` and requires GitHub CLI for attestations and upload.
It does not create or move tags, publish a release, or replace an existing asset.
Keep the field names and signature policy backward compatible for old release
assets when changing the scanner or the ZIP structure.

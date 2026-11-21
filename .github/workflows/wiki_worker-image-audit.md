# Worker Image Audit workflow

The workflow resolves the exact worker OCI digest after the repository's CI/CD
main deployment succeeds. Scheduled and manual main runs prefer the latest
stable GitHub release with verified evidence and fall back for older releases
that lack the asset. It installs a SHA256-verified Trivy archive and archives a
digest-bound CycloneDX SBOM with vulnerability findings and a status summary.

Use **Worker Image Audit → Run workflow** on `main` for a manual refresh. Supply
`release_tag` to attach evidence to an existing stable release after its exact
commit has passed Jenkins and RC. Publishing a GitHub release also triggers the
attachment path. The workflow verifies the attestation and reuses an existing
matching attachment. It leaves tag creation and release publishing to the operator.
The workflow reads Actions artifacts and packages. It does not deploy images,
run worker containers or modify production. Findings do not fail the workflow.
A missing prior deployed artifact produces a skip summary. Scanner, checksum
or identity errors fail the audit and write an error summary without an SBOM.
Keep the Trivy release pins and `scripts/worker_image_audit.py` in sync. Do not
replace the separate, read-only scan and exact-asset publication permissions.

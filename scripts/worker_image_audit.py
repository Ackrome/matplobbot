"""Generate a report-only CycloneDX worker inventory and vulnerability report."""

import argparse
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

from release_manifest import validate, verify_rc_acceptance

SCANNER_VERSION = "0.76.2"
BOM_NAME = "worker.cdx.json"
SUMMARY_NAME = "worker-audit.json"


def inspect_bom(bom, manifest, *, scanner_version=SCANNER_VERSION):
    image = manifest["images"]["worker"]
    metadata = bom["metadata"]
    component = metadata["component"]
    properties = {prop["name"]: prop["value"] for prop in component.get("properties", [])}
    if (
        bom.get("bomFormat") != "CycloneDX"
        or component.get("type") != "container"
        or component.get("name") != image
        or properties.get("aquasecurity:trivy:Labels:org.opencontainers.image.revision")
        != manifest["commit"]
    ):
        raise ValueError("SBOM does not identify the accepted worker digest and revision")
    if not any(
        tool.get("name") == "trivy" and tool.get("version") == scanner_version
        for tool in metadata["tools"]["components"]
    ):
        raise ValueError("SBOM does not identify the pinned Trivy version")
    components = bom["components"]
    packages = [unquote(item.get("purl", "")) for item in components]
    inventory = {
        "chromium": any(purl.startswith("pkg:deb/debian/chromium@") for purl in packages),
        "texlive_latex": any(
            purl.startswith("pkg:deb/debian/texlive-latex-base@") for purl in packages
        ),
        "mermaid_cli": any(
            purl.startswith("pkg:npm/@mermaid-js/mermaid-cli@") for purl in packages
        ),
    }
    vulnerabilities = bom.get("vulnerabilities", [])
    if not isinstance(vulnerabilities, list):
        raise ValueError("Invalid CycloneDX vulnerability collection")
    return {
        "inventory": inventory,
        "components_count": len(components),
        "vulnerabilities_count": len(vulnerabilities),
    }


def audit(baseline, scanner, output, report):
    if baseline.get("status") == "already_published":
        return {"status": "skipped", "reason": "versioned_release_evidence_already_verified"}
    if baseline.get("status") == "unsupported":
        return {"status": "skipped", "reason": "no_trusted_published_worker_digest"}
    if baseline.get("status") != "passed":
        return {"status": "error", "reason": "trusted_release_evidence_unavailable"}
    manifest = validate(baseline["manifest"])
    verify_rc_acceptance(manifest)
    report.update(
        commit=manifest["commit"],
        image=manifest["images"]["worker"],
        evidence_run_id=baseline["run_id"],
    )
    report["phase"] = "scan_worker_image"
    with tempfile.TemporaryDirectory(prefix="worker-sbom-", dir=output) as temporary:
        result = Path(temporary) / BOM_NAME
        subprocess.run(
            [
                str(scanner.resolve()),
                "image",
                "--quiet",
                "--image-src",
                "remote",
                "--platform",
                "linux/amd64",
                "--scanners",
                "vuln",
                "--pkg-types",
                "os,library",
                "--format",
                "cyclonedx",
                "--exit-code",
                "0",
                "--timeout",
                "15m",
                "--output",
                str(result),
                report["image"],
            ],
            check=True,
            timeout=930,
        )
        report["phase"] = "verify_worker_inventory"
        details = inspect_bom(json.loads(result.read_bytes()), manifest)
        if not all(details["inventory"].values()):
            return {"status": "error", "reason": "required_worker_inventory_incomplete", **details}
        result.replace(output / BOM_NAME)
    return {"status": "passed", **details}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--scanner", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name in (BOM_NAME, SUMMARY_NAME):
        (output / name).unlink(missing_ok=True)
    report = {
        "version": 1,
        "started_at": datetime.now(UTC).isoformat(),
        "status": "error",
        "scanner_version": SCANNER_VERSION,
        "findings_policy": "report_only",
        "phase": "resolve_worker_image",
    }
    try:
        report.update(audit(json.loads(args.baseline.read_bytes()), args.scanner, output, report))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        report.update(reason="worker_image_audit_incomplete", error_type=type(exc).__name__)
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        (output / SUMMARY_NAME).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    message = f"Worker image audit: {report['status']} ({report.get('reason', 'findings are report-only')})"
    print(message)
    if summary := os.getenv("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as step_summary:
            step_summary.write(message + "\n")
            if report["status"] == "passed":
                step_summary.write(f"- Worker: `{report['image']}`\n")
                step_summary.write(f"- Reported advisories: {report['vulnerabilities_count']}\n")
    raise SystemExit(int(report["status"] == "error"))


if __name__ == "__main__":
    main()

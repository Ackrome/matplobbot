"""Install release parameters and pin Jenkinsfile SCM before queuing a deployment."""

import argparse
import base64
import ipaddress
import json
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

DEFINITIONS = {
    "SOURCE_COMMIT": "hudson.model.StringParameterDefinition",
    "RELEASE_MANIFEST_B64": "hudson.model.TextParameterDefinition",
}


def configure(xml):
    """Pin the known Git pipeline and parameters; refuse unrelated job definitions."""
    root = ET.fromstring(xml, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
    definition = root.find("definition")
    if (
        definition is None
        or definition.get("class") != "org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition"
    ):
        raise ValueError("Expected the existing Pipeline script from SCM job")
    scm = definition.find("scm")
    if (
        scm is None
        or scm.get("class") != "hudson.plugins.git.GitSCM"
        or definition.findtext("scriptPath") != "Jenkinsfile.groovy"
    ):
        raise ValueError("Unexpected Jenkins SCM or pipeline script path; review job configuration")
    branches = scm.findall("branches/hudson.plugins.git.BranchSpec/name")
    if len(branches) != 1 or branches[0].text not in {"*/main", "main", "${SOURCE_COMMIT}"}:
        raise ValueError("Unexpected Jenkins SCM branch configuration; refusing to replace it")
    changed = []
    if branches[0].text != "${SOURCE_COMMIT}":
        branches[0].text = "${SOURCE_COMMIT}"
        changed.append("SCM_BRANCH")
    lightweight = definition.find("lightweight")
    if lightweight is None:
        lightweight = ET.SubElement(definition, "lightweight")
    if lightweight.text != "false":
        lightweight.text = "false"
        changed.append("FULL_SCM_CHECKOUT")
    properties = root.find("properties")
    if properties is None:
        properties = ET.SubElement(root, "properties")
    property_node = properties.find("hudson.model.ParametersDefinitionProperty")
    if property_node is None:
        property_node = ET.SubElement(properties, "hudson.model.ParametersDefinitionProperty")
    parameters = property_node.find("parameterDefinitions")
    if parameters is None:
        parameters = ET.SubElement(property_node, "parameterDefinitions")
    existing = {item.findtext("name"): item for item in parameters}
    for name, kind in DEFINITIONS.items():
        if name in existing:
            if existing[name].tag != kind:
                raise ValueError(
                    f"Existing {name} has an unexpected parameter type; review the job"
                )
            default = existing[name].find("defaultValue")
            if default is None:
                default = ET.SubElement(existing[name], "defaultValue")
            if default.text:
                default.text = ""
                changed.append(name + "_EMPTY_DEFAULT")
            continue
        definition = ET.SubElement(parameters, kind)
        ET.SubElement(definition, "name").text = name
        ET.SubElement(
            definition, "description"
        ).text = "Required immutable release input from the accepted CI run"
        ET.SubElement(definition, "defaultValue").text = ""
        changed.append(name)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), changed


def install(fetch, job, apply=False):
    """Read/compare/write/verify; fetch never logs configuration or credentials."""
    original = fetch(job + "/config.xml")
    updated, changed = configure(original)
    if not changed:
        return []
    if not apply:
        return changed
    if fetch(job + "/config.xml") != original:
        raise RuntimeError("Job configuration changed during preparation; retry after review")
    crumb = fetch(job.split("/job/", 1)[0] + "/crumbIssuer/api/json", optional=True)
    headers = {}
    if crumb:
        data = json.loads(crumb)
        name, value = data["crumbRequestField"], data["crumb"]
        if not re.fullmatch(r"[A-Za-z0-9-]+", name) or any(char in value for char in "\r\n"):
            raise ValueError("Invalid Jenkins crumb header")
        headers[name] = value
    fetch(job + "/config.xml", data=updated, headers=headers)
    _, remaining = configure(fetch(job + "/config.xml"))
    if remaining:
        raise RuntimeError("Jenkins did not retain required release parameters and SCM binding")
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-url", required=True)
    parser.add_argument(
        "--resolve-ip", required=True, help="Previously verified private Jenkins IPv4"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Save release definitions and SCM binding; no build is queued",
    )
    args = parser.parse_args()
    job = args.job_url.rstrip("/")
    url = urlsplit(job)
    address = ipaddress.IPv4Address(args.resolve_ip)
    if (
        url.scheme not in {"http", "https"}
        or url.username
        or url.query
        or url.fragment
        or not url.hostname
        or "/job/" not in url.path
        or not address.is_private
    ):
        parser.error("Expected an existing Jenkins job origin and private IPv4")
    port = url.port or (443 if url.scheme == "https" else 80)
    credentials = os.environ["JENKINS_USER"] + ":" + os.environ["JENKINS_TOKEN"]
    authorization = base64.b64encode(credentials.encode()).decode()
    with tempfile.TemporaryDirectory(prefix="mpb-jenkins-parameters-") as directory:
        private = Path(directory)
        cookie = private / "cookies"

        def fetch(endpoint, data=None, headers=None, optional=False):
            command = [
                "curl",
                "--silent",
                "--show-error",
                "--globoff",
                "--max-time",
                "30",
                "--noproxy",
                f"{url.hostname},{address}",
                "--resolve",
                f"{url.hostname}:{port}:{address}",
                "--cookie",
                str(cookie),
                "--cookie-jar",
                str(cookie),
                "--config",
                "-",
                "--write-out",
                "\n%{http_code}",
                "--url",
                endpoint,
            ]
            if data is not None:
                body = private / "config.xml"
                with os.fdopen(
                    os.open(body, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb"
                ) as output:
                    output.write(data)
                command += [
                    "--header",
                    "Content-Type: application/xml",
                    "--data-binary",
                    "@" + str(body),
                ]
            for name, value in (headers or {}).items():
                command += ["--header", name + ": " + value]
            # Token stays off argv, logs and saved config; do not follow redirects.
            result = subprocess.run(
                command,
                input=f'header = "Authorization: Basic {authorization}"\n'.encode(),
                capture_output=True,
            )
            body, _, status = result.stdout.rpartition(b"\n")
            if result.returncode:
                raise RuntimeError("Jenkins parameter request failed; no deployment was queued")
            if optional and status == b"404":
                return None  # API-token auth also works when CSRF protection is disabled.
            if status not in {b"200", b"204"}:
                raise RuntimeError(
                    "Jenkins denied or failed parameter configuration (HTTP "
                    + status.decode("ascii", errors="replace")
                    + "). Grant the CI identity job Read/Configure or install these definitions through an authorized operator before retrying. No deployment was queued."
                )
            return body

        changed = install(fetch, job, args.apply)
        if changed and not args.apply:
            raise SystemExit(
                "Release job changes needed: "
                + ", ".join(changed)
                + ". Dry run only; use --apply to install without running a build."
            )
        print(
            "Jenkins immutable-release parameters and Jenkinsfile SCM binding verified. No build was queued."
        )


if __name__ == "__main__":
    main()

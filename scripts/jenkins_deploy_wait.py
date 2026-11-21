"""Submit one accepted release and follow its Jenkins build through smoke verification."""

import argparse
import base64
import ipaddress
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from release_manifest import COMMIT_RE, validate

PARAMETERS_TREE = "property[parameterDefinitions[name]]"
QUEUE_TREE = "id,cancelled,executable[number,url]"
BUILD_TREE = "number,queueId,building,inProgress,result"
SMOKE_ARTIFACT = "release-smoke.json"
FAILURE_ARTIFACT = "release-failure.json"
TRANSIENT_STATUSES = {408, 429, 500, 502, 503, 504}
PREPARE_FAILURE_CODES = {
    "production_release_pending",
    "production_tracked_changes",
    "production_untracked_inputs",
    "production_release_state_mismatch",
    "production_disk_check_failed",
    "production_worker_policy_check_failed",
    "production_checkout_unavailable",
}
FAILURE_CODES = {
    "Pin Accepted Source": {"source_verification_failed"},
    "Production Preflight": {
        *PREPARE_FAILURE_CODES,
        "production_preflight_failed",
        "production_ssh_pin_failed",
        "production_preflight_timeout",
        "production_ssh_failed",
    },
    "Pre-Deploy Quality Gate": {"quality_gate_failed"},
    "Deploy to Production": {"production_deploy_failed", *PREPARE_FAILURE_CODES},
    "Post-Deploy Smoke Checks": {"smoke_failed"},
}


class DeploymentError(RuntimeError):
    """A sanitized failure safe to display in GitHub Actions."""


class JenkinsConnectionError(DeploymentError):
    """Transport outcome is unknown. Only reads may be retried automatically."""


class JenkinsTransport:
    def __init__(self, job_url, ip, username, token, private):
        url = urlsplit(job_url)
        port = url.port or (443 if url.scheme == "https" else 80)
        self.origin = f"{url.scheme}://{url.hostname}:{port}"
        self.job_path = url.path.rstrip("/")
        self.pin = f"{url.hostname}:{port}:{ip}"
        credentials = base64.b64encode(f"{username}:{token}".encode()).decode()
        self.curl_auth = f'header = "Authorization: Basic {credentials}"\n'.encode()
        self.private = private

    def request(self, path, *, form=None, timeout=30):
        headers = self.private / "response-headers"
        command = [
            "curl",
            "--disable",
            "--silent",
            "--show-error",
            "--globoff",
            "--proto",
            "=http,https",
            "--noproxy",
            "*",
            "--resolve",
            self.pin,
            "--max-time",
            f"{timeout:.3f}",
            "--max-filesize",
            "262144",
            "--dump-header",
            str(headers),
            "--config",
            "-",
            "--write-out",
            "\n%{http_code}",
            "--url",
            self.origin + path,
        ]
        if form is not None:
            body = self.private / "deployment-form"
            body.write_bytes(urlencode(form).encode())
            command += [
                "--header",
                "Content-Type: application/x-www-form-urlencoded",
                "--data-binary",
                "@" + str(body),
            ]
        try:
            response = subprocess.run(
                command,
                input=self.curl_auth,
                capture_output=True,
                timeout=timeout + 2,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise JenkinsConnectionError("Jenkins connection failed") from None
        if response.returncode:
            raise JenkinsConnectionError("Jenkins connection failed")
        content, _, status = response.stdout.rpartition(b"\n")
        final_headers = headers.read_bytes().rstrip().split(b"\r\n\r\n")[-1]
        locations = re.findall(rb"^Location:\s*([^\r\n]+)", final_headers, re.I | re.M)
        location = locations[0].strip().decode("latin-1") if len(locations) == 1 else ""
        return int(status), location, content


def _json_object(body):
    try:
        result = json.loads(body)
    except (UnicodeError, ValueError):
        raise DeploymentError("Jenkins returned an invalid JSON response") from None
    if not isinstance(result, dict):
        raise DeploymentError("Jenkins returned an invalid object")
    return result


def _absolute_path(link):
    # Jenkins may advertise another configured origin. Only use the recognized
    # path, reconstructing every request and link from the verified LAN origin.
    link = urlsplit(link)
    if link.scheme not in {"", "http", "https"} or link.query or link.fragment:
        raise DeploymentError("Jenkins returned an invalid queue or build link")
    return link.path


def _failure_summary(transport, build, commit, number, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None
    try:
        status, _, content = transport.request(
            build + "artifact/" + FAILURE_ARTIFACT, timeout=min(10, remaining)
        )
        if status != 200:
            return None
        data = _json_object(content)
    except DeploymentError:
        return None
    if (
        set(data) != {"commit", "number", "stage", "code"}
        or data["commit"] != commit
        or type(data["number"]) is not int
        or data["number"] != number
    ):
        return None
    stage, code = data["stage"], data["code"]
    if isinstance(stage, str) and isinstance(code, str) and code in FAILURE_CODES.get(stage, ()):
        return f"Jenkins failure in {stage}: `{code}`."
    return None


def deploy(transport, commit, manifest, deploy_host, *, timeout=2400, interval=5, report=print):
    """Submit once, follow the exact queue ID, and verify its immutable smoke artifact."""
    job = transport.job_path
    preflight = job + "/api/json?" + urlencode({"tree": PARAMETERS_TREE})
    status, _, body = transport.request(preflight)
    if status != 200:
        raise DeploymentError(f"Jenkins parameter preflight returned HTTP {status}")
    properties = _json_object(body).get("property", [])
    names = {p["name"] for prop in properties for p in prop.get("parameterDefinitions", [])}
    if not {"SOURCE_COMMIT", "RELEASE_MANIFEST_B64", "DEPLOY_HOST"} <= names:
        raise DeploymentError("Required Jenkins job parameters are missing")

    try:
        status, location, _ = transport.request(
            job + "/buildWithParameters",
            form={
                "SOURCE_COMMIT": commit,
                "RELEASE_MANIFEST_B64": base64.b64encode(manifest).decode(),
                "DEPLOY_HOST": deploy_host,
            },
        )
    except JenkinsConnectionError:
        raise DeploymentError(
            "Jenkins dispatch outcome is unknown. Check Jenkins before retrying."
        ) from None
    # Jenkins returns 303 and the same queue location for an identical queued job.
    if status not in {201, 303}:
        raise DeploymentError(
            f"Jenkins dispatch returned HTTP {status}. Check Jenkins before retrying."
        )
    queue = re.fullmatch(r"/queue/item/([1-9][0-9]*)/?", _absolute_path(location))
    if queue is None:
        raise DeploymentError(
            "Jenkins accepted dispatch without a valid queue ID. Check Jenkins before retrying."
        )
    queue_id = int(queue[1])
    queue_path = f"/queue/item/{queue_id}/"
    report(
        f"Queued Jenkins deployment for `{commit}`. [Queue item {queue_id}]({transport.origin + queue_path})"
    )

    deadline = time.monotonic() + timeout

    def poll(path, state, complete, *, retry_missing=False):
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                code, _, content = transport.request(path, timeout=min(30, remaining))
            except JenkinsConnectionError:
                code = 503
            if code == 200:
                result = complete(_json_object(content))
                if result is not None:
                    return result
            elif code not in TRANSIENT_STATUSES and (code != 404 or not retry_missing):
                raise DeploymentError(f"Jenkins {state} returned HTTP {code}")
            time.sleep(min(interval, max(0, deadline - time.monotonic())))
        raise DeploymentError(
            f"Timed out waiting for Jenkins {state}. Jenkins may still be running."
        )

    def executable(data):
        if data.get("id") != queue_id or data.get("cancelled"):
            raise DeploymentError("Jenkins queue item is cancelled or its ID changed")
        item = data.get("executable")
        if item is None:
            return None
        number = item.get("number")
        if (
            type(number) is not int
            or number < 1
            or _absolute_path(item.get("url", "")) != f"{job}/{number}/"
        ):
            raise DeploymentError("Jenkins queue item does not reference the expected job")
        return number

    number = poll(queue_path + "api/json?" + urlencode({"tree": QUEUE_TREE}), "queue", executable)
    build = f"{job}/{number}/"
    report(f"[Jenkins build #{number}]({transport.origin + build}) started for `{commit}`.")

    def build_result(data):
        if data.get("number") != number or data.get("queueId") != queue_id:
            raise DeploymentError("Jenkins build number or queue ID differs from this dispatch")
        if (
            data.get("building") is True
            or data.get("inProgress") is True
            or data.get("result") is None
        ):
            return None
        result = data["result"]
        if data.get("building") is not False or data.get("inProgress") is not False:
            raise DeploymentError(f"Jenkins build #{number} returned an invalid completion state")
        known = {"SUCCESS", "FAILURE", "ABORTED", "UNSTABLE", "NOT_BUILT"}
        return result if isinstance(result, str) and result in known else "an unexpected result"

    result = poll(
        build + "api/json?" + urlencode({"tree": BUILD_TREE}),
        "build result",
        build_result,
        retry_missing=True,
    )
    if result != "SUCCESS":
        if result == "FAILURE":
            detail = _failure_summary(transport, build, commit, number, deadline)
            if detail:
                report(detail)
        raise DeploymentError(f"Jenkins build #{number} finished with {result}")

    def verify_smoke(data):
        if data != {"commit": commit, "number": number, "status": "smoke_verified"}:
            raise DeploymentError(
                "Jenkins smoke proof does not match the accepted commit and build"
            )
        return True

    poll(build + "artifact/" + SMOKE_ARTIFACT, "smoke proof", verify_smoke, retry_missing=True)
    report(
        f"Jenkins build #{number} passed smoke tests and finalized `{commit}`. [Build]({transport.origin + build})"
    )


def _private_ipv4(address):
    address = ipaddress.IPv4Address(address)
    if not any(
        address in ipaddress.IPv4Network(net)
        for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    ):
        raise DeploymentError("Jenkins and app hosts must use verified RFC1918 addresses")
    return str(address)


def _report(message):
    print(message, flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as output:
            output.write(message + "\n\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-url", required=True)
    parser.add_argument("--resolve-ip", required=True)
    parser.add_argument("--deploy-host", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        if not re.fullmatch(
            r"https?://[a-zA-Z0-9.-]+(?::[0-9]{1,5})?/job/matplobbot-deploy/?", args.job_url
        ):
            raise DeploymentError("Invalid LAN Jenkins deployment job URL")
        jenkins = _private_ipv4(args.resolve_ip)
        host = _private_ipv4(args.deploy_host)
        username = os.environ.get("JENKINS_USER")
        token = os.environ.get("JENKINS_TOKEN")
        if not username or not token:
            raise DeploymentError("Jenkins CI credentials are missing")
        with args.manifest.open("rb") as source:
            manifest = source.read(2_000_001)
        if len(manifest) > 2_000_000 or not COMMIT_RE.fullmatch(args.commit):
            raise DeploymentError("Invalid release manifest length or commit")
        accepted = validate(json.loads(manifest))
        evidence = accepted.get("acceptance", {})
        if (
            accepted["commit"] != args.commit
            or evidence.get("commit") != args.commit
            or evidence.get("status") != "passed"
            or evidence.get("restore_verified") is not True
            or evidence.get("images") != accepted["images"]
        ):
            raise DeploymentError(
                "Manifest does not attest RC and restore for the requested commit"
            )
        with tempfile.TemporaryDirectory(prefix="mpb-jenkins-wait-") as directory:
            transport = JenkinsTransport(args.job_url, jenkins, username, token, Path(directory))
            deploy(transport, args.commit, manifest, host, report=_report)
    except DeploymentError as exc:
        _report(f"Deployment verification failed. {exc}")
        return 1
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        _report(
            "Deployment verification failed. Invalid input or response. Check Jenkins before retrying."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

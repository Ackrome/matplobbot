"""Resolve accepted immutable release evidence from a successful main deployment."""

import argparse
import hashlib
import io
import json
import os
import re
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from release_manifest import COMMIT_RE, validate, verify_rc_acceptance

WORKFLOW = ".github/workflows/ci-cd.yml"
DEPLOY_JOB = "Deploy and Verify Jenkins Smoke"
MANIFEST_NAME = "release-manifest-accepted.json"
MAX_MANIFEST_BYTES = 2_000_000
MAX_ARTIFACT_BYTES = 20_000_000


class BaselineUnavailable(RuntimeError):
    """The workflow could not prove a deployed release."""


class HttpsRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != "https":
            raise ValueError("Artifact redirects must use HTTPS")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class ReleaseEvidence:
    def __init__(self, repository, token):
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", repository) or not token:
            raise ValueError("GitHub repository and read token are required")
        self.repository = repository
        self.root = f"https://api.github.com/repos/{repository}"
        self.token = token
        self.opener = build_opener(HttpsRedirects())

    def read(self, path, limit, *, accept="application/vnd.github+json"):
        request = Request(
            self.root + path,
            headers={"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"},
        )
        # An Actions artifact can redirect to a temporary external download URL.
        request.add_unredirected_header("Authorization", f"Bearer {self.token}")
        with self.opener.open(request, timeout=30) as response:
            body = response.read(limit + 1)
        if len(body) > limit:
            raise ValueError("Release evidence exceeds the allowed size")
        return body

    def get(self, path):
        return json.loads(self.read(path, MAX_MANIFEST_BYTES))

    def deployed(self, run):
        if (
            run.get("event") != "push"
            or run.get("head_branch") != "main"
            or run.get("path") != WORKFLOW
            or run.get("status") != "completed"
            or (run.get("head_repository") or {}).get("full_name", "").lower()
            != self.repository.lower()
            or not COMMIT_RE.fullmatch(run.get("head_sha", ""))
            or type(run.get("id")) is not int
        ):
            return None
        jobs = self.get(f"/actions/runs/{run['id']}/jobs?filter=latest&per_page=100")["jobs"]
        deployed = [
            job
            for job in jobs
            if job.get("name") == DEPLOY_JOB and job.get("conclusion") == "success"
        ]
        if len(deployed) == 1 and deployed[0].get("completed_at"):
            return deployed[0]
        return None

    def resolve(self, *, run_id=None, exclude_commit=None, commit=None):
        path = (
            "/actions/workflows/ci-cd.yml/runs?branch=main&event=push&status=completed&per_page=20"
        )
        if commit is not None:
            if not COMMIT_RE.fullmatch(commit):
                raise ValueError("Expected a full release commit")
            path += "&head_sha=" + commit
        runs = (
            [self.get(f"/actions/runs/{run_id}")]
            if run_id is not None
            else self.get(path)["workflow_runs"]
        )
        deployed = [
            (run, job)
            for run in runs
            if run.get("head_sha") != exclude_commit
            and (commit is None or run.get("head_sha") == commit)
            and (job := self.deployed(run)) is not None
        ]
        if not deployed:
            raise BaselineUnavailable("no_successful_deployment")
        run, job = max(deployed, key=lambda item: item[1]["completed_at"])
        commit = run["head_sha"]
        name = f"accepted-release-{commit}"
        artifacts = self.get(f"/actions/runs/{run['id']}/artifacts?name={name}")["artifacts"]
        matches = [
            item
            for item in artifacts
            if item.get("name") == name
            and item.get("expired") is False
            and type(item.get("id")) is int
        ]
        if len(matches) != 1:
            raise BaselineUnavailable("accepted_artifact_unavailable")
        artifact = matches[0]
        archive = self.read(f"/actions/artifacts/{artifact['id']}/zip", MAX_ARTIFACT_BYTES)
        if artifact.get("digest") != "sha256:" + hashlib.sha256(archive).hexdigest():
            raise ValueError("Accepted artifact checksum differs from Actions metadata")
        with zipfile.ZipFile(io.BytesIO(archive)) as evidence:
            members = [member for member in evidence.infolist() if member.filename == MANIFEST_NAME]
            if len(members) != 1 or members[0].file_size > MAX_MANIFEST_BYTES:
                raise ValueError("Invalid accepted release manifest member")
            manifest = validate(json.loads(evidence.read(members[0])))
        verify_rc_acceptance(manifest)
        if manifest["commit"] != commit or str(manifest.get("ci_run")) != str(run["id"]):
            raise ValueError("Accepted evidence differs from the deployed Actions run")
        return {
            "status": "passed",
            "run_id": run["id"],
            "deployment_job_id": job["id"],
            "artifact_id": artifact["id"],
            "artifact_digest": artifact["digest"],
            "manifest": manifest,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--exclude-commit")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.unlink(missing_ok=True)
    try:
        source = ReleaseEvidence(os.getenv("GITHUB_REPOSITORY", ""), os.getenv("GH_TOKEN", ""))
        evidence = source.resolve(run_id=args.run_id, exclude_commit=args.exclude_commit)
    except BaselineUnavailable as exc:
        evidence = {"status": "unsupported", "reason": str(exc)}
    except (HTTPError, URLError, OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile):
        evidence = {"status": "error", "reason": "release_evidence_unavailable_or_invalid"}
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    if evidence["status"] != "passed":
        print(f"Release baseline {evidence['status']}: {evidence['reason']}")
    raise SystemExit(int(evidence["status"] == "error"))


if __name__ == "__main__":
    main()

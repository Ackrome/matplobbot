"""Validate or publish a reviewed curriculum bundle through the administrator API."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import sys
import tempfile
import time
from datetime import UTC, date, datetime
from pathlib import Path, PureWindowsPath
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_JSON_BYTES = 64 * 1024 * 1024
ASSESSMENT_FIELDS = (
    "discipline_code",
    "discipline_name",
    "semester",
    "kind",
    "page",
    "evidence",
)
METADATA_FIELDS = (
    "title",
    "source_url",
    "program",
    "profile",
    "campus",
    "admission_year",
    "study_form",
    "scan_layout",
)
KINDS = {"exam", "pass", "graded_pass", "coursework", "course_project"}
LAYOUTS = {None, "fa_legacy_v1", "fa_compact_v1"}
COHORT_FIELDS = ("program", "profile", "campus", "admission_year", "study_form")


class BundleError(ValueError):
    """An actionable error whose message never contains credentials or HTTP bodies."""


def _require(condition, message):
    if not condition:
        raise BundleError(message)


def _keys(value, required, optional=()):
    _require(isinstance(value, dict), "Expected a JSON object")
    _require(
        set(required) <= value.keys() <= set(required) | set(optional),
        "Unexpected or missing JSON fields",
    )


def _text(value, maximum):
    _require(isinstance(value, str) and 0 < len(value.strip()) <= maximum, "Invalid text field")
    _require(not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value), "Invalid control character")
    return value.strip()


def _integer(value, minimum, maximum):
    _require(type(value) is int and minimum <= value <= maximum, "Invalid integer field")
    return value


def official_url(value):
    value = _text(value, 2048)
    _require(not re.search(r"[\x00-\x20\x7f]", value), "Invalid official document URL")
    try:
        parts = urlsplit(value)
        valid = (
            parts.scheme == "https"
            and parts.hostname in {"fa.ru", "www.fa.ru"}
            and parts.port in (None, 443)
            and not parts.username
            and not parts.password
        )
    except ValueError as exc:
        raise BundleError("Invalid official document URL") from exc
    path = parts.path
    for _ in range(3):
        path = unquote(path)
    _require(
        valid
        and path.startswith("/upload/")
        and "\\" not in path
        and "%" not in path
        and not any(segment in {".", ".."} for segment in path.split("/"))
        and not re.search(r"[\x00-\x1f\x7f]", path),
        "Unsupported official document URL",
    )
    return urlunsplit(("https", parts.hostname, parts.path, parts.query, ""))


def validate_base_url(value):
    try:
        parts = urlsplit(value)
        _ = parts.port
    except ValueError as exc:
        raise BundleError("Invalid API origin") from exc
    _require(
        parts.scheme in {"http", "https"}
        and parts.hostname
        and not parts.username
        and not parts.password
        and parts.path in {"", "/"}
        and not parts.query
        and not parts.fragment
        and not re.search(r"[\x00-\x20\x7f]", value),
        "Invalid API origin",
    )
    if parts.scheme == "http":
        try:
            loopback = ipaddress.ip_address(parts.hostname).is_loopback
        except ValueError:
            loopback = parts.hostname == "localhost"
        _require(loopback, "HTTP authentication is permitted only on loopback; use HTTPS remotely")
    return value.rstrip("/")


def validate_assessments(rows):
    _require(
        isinstance(rows, list) and 1 <= len(rows) <= 5000, "Expected 1 to 5000 reviewed assessments"
    )
    cleaned, identities, names = [], set(), {}
    for row in rows:
        _keys(row, ASSESSMENT_FIELDS)
        item = {
            key: _text(row[key], size)
            for key, size in (
                ("discipline_code", 100),
                ("discipline_name", 500),
                ("evidence", 2000),
            )
        }
        item.update(semester=_integer(row["semester"], 1, 16), page=_integer(row["page"], 1, 100))
        _require(isinstance(row["kind"], str) and row["kind"] in KINDS, "Invalid assessment kind")
        item["kind"] = row["kind"]
        identity = item["discipline_code"], item["semester"], item["kind"]
        _require(identity not in identities, "Duplicate assessment identity")
        identities.add(identity)
        canonical = " ".join(item["discipline_name"].casefold().split())
        previous = names.setdefault(item["discipline_code"], canonical)
        _require(previous == canonical, "Conflicting discipline names for one identity")
        cleaned.append(item)
    return sorted(cleaned, key=lambda item: tuple(str(item[key]) for key in ASSESSMENT_FIELDS))


def validate_groups(groups):
    _require(isinstance(groups, list) and len(groups) <= 100, "Expected at most 100 groups")
    cleaned, ids = [], set()
    for group in groups:
        _keys(group, ("group_id", "group_name", "terms"))
        group_id = _text(group["group_id"], 128)
        _require(
            not re.search(r"[/\\?#\x00]", group_id) and group_id not in ids,
            "Invalid or duplicate group ID",
        )
        ids.add(group_id)
        terms = group["terms"]
        _require(
            isinstance(terms, list) and 1 <= len(terms) <= 16, "Expected 1 to 16 semester ranges"
        )
        normalized, semesters = [], set()
        for term in terms:
            _keys(term, ("semester", "start_date", "end_date"))
            semester = _integer(term["semester"], 1, 16)
            _require(semester not in semesters, "Duplicate semester")
            semesters.add(semester)
            try:
                start, end = (date.fromisoformat(term[key]) for key in ("start_date", "end_date"))
            except (ValueError, TypeError) as exc:
                raise BundleError("Invalid semester date") from exc
            _require(0 <= (end - start).days <= 400, "Invalid semester range")
            _require(
                start.isoformat() == term["start_date"] and end.isoformat() == term["end_date"],
                "Use ISO YYYY-MM-DD dates",
            )
            normalized.append(
                {"semester": semester, "start_date": start.isoformat(), "end_date": end.isoformat()}
            )
        normalized.sort(key=lambda term: term["start_date"])
        _require(
            all(a["end_date"] < b["start_date"] for a, b in zip(normalized, normalized[1:])),
            "Overlapping semester ranges",
        )
        cleaned.append(
            {
                "group_id": group_id,
                "group_name": _text(group["group_name"], 255),
                "terms": normalized,
            }
        )
    return sorted(cleaned, key=lambda group: group["group_id"])


def _pdf_bytes(document):
    path = document["pdf_path"].resolve()
    _require(
        path.is_relative_to(document["bundle_dir"]) and path.is_file(),
        "PDF is outside the bundle directory",
    )
    _require(0 < path.stat().st_size <= MAX_PDF_BYTES, "PDF exceeds the 20 MiB limit")
    with path.open("rb") as stream:
        content = stream.read(MAX_PDF_BYTES + 1)
    _require(
        len(content) <= MAX_PDF_BYTES and content.lstrip().startswith(b"%PDF-"),
        "Invalid PDF signature or size",
    )
    _require(
        hashlib.sha256(content).hexdigest() == document["source_sha256"], "PDF SHA256 mismatch"
    )
    return content


def load_bundle(path):
    path = Path(path).resolve()
    _require(path.stat().st_size <= MAX_JSON_BYTES, "Bundle JSON exceeds the limit")
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise BundleError("Invalid bundle JSON") from exc
    _keys(bundle, ("version", "documents"))
    _require(
        type(bundle["version"]) is int and bundle["version"] == 1, "Unsupported bundle version"
    )
    _require(
        isinstance(bundle["documents"], list) and 1 <= len(bundle["documents"]) <= 25,
        "Expected 1 to 25 documents",
    )
    documents, sources, group_ids = [], set(), set()
    for entry in bundle["documents"]:
        _keys(
            entry,
            ("metadata", "source_sha256", "pdf_file", "assessments", "groups"),
            ("parent_source_url",),
        )
        metadata = entry["metadata"]
        _keys(metadata, METADATA_FIELDS[:-1], ("scan_layout",))
        metadata = {**metadata, "scan_layout": metadata.get("scan_layout")}
        for key, maximum in (
            ("title", 500),
            ("program", 500),
            ("profile", 500),
            ("campus", 255),
            ("study_form", 100),
        ):
            metadata[key] = _text(metadata[key], maximum)
        metadata["admission_year"] = _integer(metadata["admission_year"], 2000, 2100)
        _require(
            metadata["scan_layout"] is None or isinstance(metadata["scan_layout"], str),
            "Invalid scan layout",
        )
        _require(metadata["scan_layout"] in LAYOUTS, "Unsupported scan layout")
        metadata["source_url"] = official_url(metadata["source_url"])
        _require(metadata["source_url"] not in sources, "Duplicate document source in bundle")
        sources.add(metadata["source_url"])
        _require(
            isinstance(entry["source_sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", entry["source_sha256"]),
            "Invalid source SHA256",
        )
        relative = _text(entry["pdf_file"], 1024)
        _require(
            not Path(relative).is_absolute()
            and not PureWindowsPath(relative).drive
            and "\\" not in relative,
            "PDF filename must be relative to the bundle",
        )
        document = {
            "metadata": metadata,
            "source_sha256": entry["source_sha256"],
            "pdf_path": path.parent / relative,
            "bundle_dir": path.parent,
            "assessments": validate_assessments(entry["assessments"]),
            "groups": validate_groups(entry["groups"]),
            "parent_source_url": official_url(entry["parent_source_url"])
            if entry.get("parent_source_url") is not None
            else None,
        }
        _pdf_bytes(document)
        for group in document["groups"]:
            _require(
                group["group_id"] not in group_ids, "Group appears in multiple bundle documents"
            )
            group_ids.add(group["group_id"])
        documents.append(document)
    by_source = {document["metadata"]["source_url"]: document for document in documents}
    for document in documents:
        parent_source = document["parent_source_url"]
        if parent_source is None:
            continue
        parent = by_source.get(parent_source)
        _require(
            parent is not None and parent is not document,
            "Supplement parent must be another root document in this bundle",
        )
        _require(
            parent["parent_source_url"] is None, "Supplement chains and cycles are not supported"
        )
        _require(not document["groups"], "Supplementary documents cannot own group bindings")
        _require(
            all(document["metadata"][key] == parent["metadata"][key] for key in COHORT_FIELDS),
            "Supplement and parent cohort metadata differ",
        )
    # The bundle may list its supporting evidence first; publication always
    # creates and verifies roots before resolving foreign keys for supplements.
    return sorted(documents, key=lambda document: document["parent_source_url"] is not None)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BundleError("API redirects are forbidden")


class AdminClient:
    """Bounded, non-redirecting HTTP transport; response/error bodies are never logged."""

    def __init__(self, base_url, username, password):
        self.base_url = validate_base_url(base_url)
        self.opener = build_opener(ProxyHandler({}), _NoRedirect())
        self.token = None
        _require(bool(username) and bool(password), "STATS_USER and STATS_PASS are required")
        result = self.request(
            "POST",
            "/api/auth/login",
            raw=urlencode({"username": username, "password": password}).encode(),
            content_type="application/x-www-form-urlencoded",
        )
        token = result.get("access_token") if isinstance(result, dict) else None
        _require(
            isinstance(token, str) and token and not re.search(r"[\r\n]", token),
            "Login returned no usable access token",
        )
        self.token = token

    def request(self, method, path, *, body=None, raw=None, content_type=None, timeout=30):
        _require(path.startswith("/api/") and not path.startswith("//"), "Invalid API path")
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if body is not None:
            raw, content_type = (
                json.dumps(body, ensure_ascii=False).encode("utf-8"),
                "application/json",
            )
        if content_type:
            headers["Content-Type"] = content_type
        request = Request(self.base_url + path, data=raw, method=method, headers=headers)
        try:
            with self.opener.open(request, timeout=timeout) as response:
                data = response.read(MAX_JSON_BYTES + 1)
                _require(len(data) <= MAX_JSON_BYTES, "API response exceeds the size limit")
                if response.status == 204:
                    return None
                return json.loads(data)
        except HTTPError as exc:
            status = exc.code
            exc.close()
            raise BundleError(f"API request failed: HTTP {status}") from None
        except (URLError, TimeoutError, OSError) as exc:
            raise BundleError("API connection failed") from exc
        except (UnicodeError, ValueError) as exc:
            if isinstance(exc, BundleError):
                raise
            raise BundleError("API returned invalid JSON") from exc


def read_registry(client):
    registry = client.request("GET", "/api/curricula")
    _require(isinstance(registry, list), "Unexpected curriculum registry response")
    details, seen = [], set()
    for item in registry:
        _require(isinstance(item, dict), "Invalid registry entry")
        identifier = _integer(item.get("id"), 1, 2**31 - 1)
        _require(identifier not in seen, "Duplicate registry identity")
        seen.add(identifier)
        detail = client.request("GET", f"/api/curricula/{identifier}")
        _require(
            isinstance(detail, dict) and detail.get("id") == identifier,
            "Mismatched document response",
        )
        details.append(detail)
    return details


def _same_records(left, right):
    return validate_assessments(left) == validate_assessments(right)


def _parent_id(document, details, *, allow_missing=False):
    source = document.get("parent_source_url")
    if source is None:
        return None
    parents = [item for item in details if item.get("source_url") == source]
    _require(len(parents) <= 1, "Multiple registered documents share the parent source URL")
    if not parents:
        _require(allow_missing, "Supplement parent has not been registered")
        return None
    parent = parents[0]
    _require(parent.get("parent_document_id") is None, "Supplement parent must be a root document")
    _require(
        all(parent.get(key) == document["metadata"][key] for key in COHORT_FIELDS),
        "Registered supplement parent has different cohort metadata",
    )
    return _integer(parent.get("id"), 1, 2**31 - 1)


def _check_existing(document, existing, parent_id=None):
    if existing is None:
        return
    _require(
        all(existing.get(key) == value for key, value in document["metadata"].items()),
        "Existing curriculum metadata conflicts with the bundle",
    )
    _require(
        existing.get("parent_document_id") == parent_id,
        "Existing curriculum parent conflicts with the bundle",
    )
    if document.get("parent_source_url"):
        _require(not existing.get("groups"), "Supplementary documents cannot own group bindings")
    digest = document["source_sha256"]
    if existing.get("published_hash"):
        _require(
            existing["published_hash"] == digest, "Refusing to replace an existing published PDF"
        )
        _require(
            _same_records(existing.get("published_assessments"), document["assessments"]),
            "Refusing to replace existing published assessments",
        )
    _require(
        not existing.get("pending_hash")
        or existing["pending_hash"] == digest
        or not existing.get("published_hash"),
        "A different PDF is pending review",
    )


def merged_groups(existing, requested):
    result = {group["group_id"]: group for group in validate_groups(existing)}
    for group in validate_groups(requested):
        previous = result.get(group["group_id"])
        _require(
            previous is None or previous == group,
            "Existing group dates or name conflict with the bundle",
        )
        result[group["group_id"]] = group
    return validate_groups(list(result.values()))


def preflight(documents, details):
    """Check every document/group conflict before the first write in the batch."""
    plans = []
    for document in documents:
        matches = [
            entry
            for entry in details
            if entry.get("source_url") == document["metadata"]["source_url"]
        ]
        _require(len(matches) <= 1, "Multiple registered documents share this source URL")
        existing = matches[0] if matches else None
        parent_id = _parent_id(document, details, allow_missing=existing is None)
        _check_existing(document, existing, parent_id)
        identifier = existing["id"] if existing else None
        requested_ids = {group["group_id"] for group in document["groups"]}
        for entry in details:
            if entry["id"] != identifier:
                _require(
                    not requested_ids.intersection(
                        group["group_id"] for group in entry.get("groups", [])
                    ),
                    "Target group is bound to another document",
                )
        merged_groups(existing.get("groups", []) if existing else [], document["groups"])
        plans.append((document, existing))
    return plans


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _backup_detail(detail):
    keys = (
        *METADATA_FIELDS,
        "parent_document_id",
        "id",
        "pending_hash",
        "published_hash",
        "page_count",
        "processing_state",
        "processing_error",
        "parser_version",
        "checked_at",
        "published_at",
    )
    result = {key: detail.get(key) for key in keys}
    result["groups"] = validate_groups(detail.get("groups", []))
    for key in ("candidates", "published_assessments"):
        result[key] = [
            {field: row.get(field) for field in ASSESSMENT_FIELDS} for row in detail.get(key, [])
        ]
    return result


def wait_ready(
    client, identifier, *, wait_seconds=420, progress=print, clock=time.monotonic, sleep=time.sleep
):
    deadline, last_state = clock() + wait_seconds, None
    while True:
        remaining = deadline - clock()
        _require(remaining > 0, "Processing did not finish before the wait deadline")
        detail = client.request("GET", f"/api/curricula/{identifier}", timeout=min(30, remaining))
        _require(
            isinstance(detail, dict) and detail.get("id") == identifier,
            "Mismatched processing response",
        )
        state = detail.get("processing_state")
        _require(state in {"ready", "queued", "processing", "error"}, "Unexpected processing state")
        if state != last_state:
            progress(f"Document {identifier}: {state}")
            last_state = state
        _require(state != "error", "Document processing failed; inspect the administrator UI")
        if state == "ready":
            return detail
        remaining = deadline - clock()
        _require(remaining > 0, "Processing did not finish before the wait deadline")
        sleep(min(5, remaining))


def publish_bundle(documents, client, output, *, apply=False, wait_seconds=420, progress=print):
    """Persist progress and pre-mutation backups; reruns preserve existing publication."""
    _require(0 < wait_seconds <= 420, "Wait deadline must be between 1 and 420 seconds")
    details = read_registry(client)
    plans = preflight(documents, details)
    report = {
        "version": 1,
        "mode": "apply" if apply else "dry_run",
        "status": "validated",
        "documents": [],
    }
    if not apply:
        report["documents"] = [
            {
                "id": existing["id"] if existing else None,
                "source_sha256": document["source_sha256"],
                "assessment_count": len(document["assessments"]),
                "group_ids": [group["group_id"] for group in document["groups"]],
                "parent_source_url": document.get("parent_source_url"),
                "action": "reuse" if existing else "create",
            }
            for document, existing in plans
        ]
        _write_json(output, report)
        return report
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup = Path(str(output) + f".before-{stamp}.json")
    _write_json(
        backup,
        {
            "version": 1,
            "created_at": stamp,
            "documents": [_backup_detail(item) for item in details],
        },
    )
    report.update(status="applying", backup_file=str(backup))
    _write_json(output, report)
    try:
        for document, _ in plans:
            # Recheck all cross-document ownership immediately before mutations.
            latest = read_registry(client)
            existing = preflight([document], latest)[0][1]
            parent_id = _parent_id(document, latest)
            content = _pdf_bytes(document)  # Detect file replacement after local validation.
            if existing is None:
                existing = client.request(
                    "POST",
                    "/api/curricula",
                    body={
                        **document["metadata"],
                        "parent_document_id": parent_id,
                    },
                )
            identifier = _integer(existing.get("id"), 1, 2**31 - 1)
            prefix = f"/api/curricula/{identifier}"
            digest = document["source_sha256"]
            if digest not in {existing.get("pending_hash"), existing.get("published_hash")}:
                client.request(
                    "PUT", prefix + "/document", raw=content, content_type="application/pdf"
                )
            existing = wait_ready(client, identifier, wait_seconds=wait_seconds, progress=progress)
            _check_existing(document, existing, parent_id)
            _require(
                (existing.get("pending_hash") or existing.get("published_hash")) == digest,
                "Imported PDF does not match the bundle SHA256",
            )
            _require(
                type(existing.get("page_count")) is int
                and all(row["page"] <= existing["page_count"] for row in document["assessments"]),
                "An assessment page is outside the imported PDF",
            )
            if not existing.get("published_hash"):
                client.request(
                    "POST",
                    prefix + "/publish",
                    body={"expected_hash": digest, "assessments": document["assessments"]},
                )
            # A publication may take time; re-read ownership before replacing bindings.
            current = preflight([document], read_registry(client))[0][1]
            _require(
                current is not None and current["id"] == identifier,
                "Registered document changed during publication",
            )
            groups = merged_groups(current.get("groups", []), document["groups"])
            if groups != validate_groups(current.get("groups", [])):
                client.request("PUT", prefix + "/groups", body={"groups": groups})
            final = client.request("GET", prefix)
            _check_existing(document, final, parent_id)
            _require(
                final.get("published_hash") == digest
                and _same_records(final.get("published_assessments"), document["assessments"]),
                "Persisted publication verification failed",
            )
            _require(
                validate_groups(final.get("groups", [])) == groups,
                "Persisted group binding verification failed",
            )
            report["documents"].append(
                {
                    "id": identifier,
                    "source_sha256": digest,
                    "published_hash": final["published_hash"],
                    "assessment_count": len(final["published_assessments"]),
                    "group_ids": [group["group_id"] for group in groups],
                    "parent_document_id": parent_id,
                    "status": "verified",
                }
            )
            _write_json(output, report)
        report["status"] = "complete"
        _write_json(output, report)
        return report
    except Exception:
        report["status"] = "failed"
        _write_json(output, report)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:9583")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Explicitly create, upload, publish and bind; default is read-only",
    )
    parser.add_argument("--wait-seconds", type=int, default=420)
    args = parser.parse_args(argv)
    try:
        documents = load_bundle(args.bundle)
        base_url = validate_base_url(args.base_url)
        _require(
            args.output.resolve() != args.bundle.resolve()
            and all(
                args.output.resolve() != document["pdf_path"].resolve() for document in documents
            ),
            "Output must not replace a bundle input",
        )
        client = AdminClient(base_url, os.getenv("STATS_USER"), os.getenv("STATS_PASS"))
        result = publish_bundle(
            documents, client, args.output, apply=args.apply, wait_seconds=args.wait_seconds
        )
        print(
            f"Curriculum bundle {result['status']}: {len(result['documents'])} documents; mode={result['mode']}"
        )
        return 0
    except BundleError as exc:
        print(f"Curriculum bundle failed: {exc}", file=sys.stderr)
    except Exception:
        # Never expose credentials, server response bodies or unexpected exception reprs.
        print("Curriculum bundle failed: unexpected local or API error", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Offline safety and idempotency checks for reviewed curriculum publication."""

import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from scripts import publish_curriculum_bundle as bundle


class FakeClient:
    def __init__(self, documents=(), first_write=None):
        self.documents = {item["id"]: copy.deepcopy(item) for item in documents}
        self.calls = []
        self.first_write = first_write

    def request(self, method, path, *, body=None, raw=None, **kwargs):
        self.calls.append((method, path))
        if method != "GET" and self.first_write:
            self.first_write()
            self.first_write = None
        if path == "/api/curricula":
            if method == "GET":
                return [{"id": identifier} for identifier in self.documents]
            identifier = max(self.documents, default=0) + 1
            self.documents[identifier] = {
                **copy.deepcopy(body),
                "id": identifier,
                "groups": [],
                "published_hash": None,
                "published_assessments": [],
                "pending_hash": None,
                "candidates": [],
                "processing_state": "ready",
            }
            return copy.deepcopy(self.documents[identifier])
        segments = path.split("/")
        document = self.documents[int(segments[3])]
        if method == "GET":
            return copy.deepcopy(document)
        action = segments[4]
        if action == "document":
            document.update(pending_hash=hashlib.sha256(raw).hexdigest(), page_count=2)
        elif action == "publish":
            if body["expected_hash"] != document["pending_hash"]:
                raise AssertionError("Incorrect publication hash")
            document.update(
                published_hash=body["expected_hash"],
                pending_hash=None,
                published_assessments=copy.deepcopy(body["assessments"]),
            )
        elif action == "groups":
            document["groups"] = copy.deepcopy(body["groups"])
        else:
            raise AssertionError("Unexpected API mutation")
        return copy.deepcopy(document)


class PublicationBundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = b"%PDF-test fixture, never parsed by the CLI"
        (self.root / "plan.pdf").write_bytes(self.source)
        self.metadata = {
            "title": "Reviewed plan",
            "source_url": "https://www.fa.ru/upload/plan.pdf",
            "program": "01.03.02",
            "profile": "Computing",
            "campus": "Moscow",
            "admission_year": 2023,
            "study_form": "Full time",
            "scan_layout": "fa_legacy_v1",
        }
        self.row = {
            "discipline_code": "scan:p1:r004",
            "discipline_name": "Math",
            "semester": 7,
            "kind": "exam",
            "page": 1,
            "evidence": "Reviewed source cell",
        }
        self.group = {
            "group_id": "162426",
            "group_name": "Test group",
            "terms": [{"semester": 7, "start_date": "2026-09-01", "end_date": "2027-01-31"}],
        }
        self.entry = {
            "metadata": self.metadata,
            "source_sha256": hashlib.sha256(self.source).hexdigest(),
            "pdf_file": "plan.pdf",
            "assessments": [self.row],
            "groups": [self.group],
        }
        self.bundle_file = self.root / "bundle.json"
        self.output = self.root / "result.json"

    def load(self, entries=None):
        self.bundle_file.write_text(
            json.dumps({"version": 1, "documents": entries or [self.entry]}), encoding="utf-8"
        )
        return bundle.load_bundle(self.bundle_file)

    def published(self, *, identifier=1, groups=None):
        return {
            **self.metadata,
            "id": identifier,
            "published_hash": self.entry["source_sha256"],
            "published_assessments": [self.row],
            "pending_hash": None,
            "candidates": [],
            "groups": groups or [],
            "page_count": 2,
            "processing_state": "ready",
        }

    def test_validation_rejects_wrong_hash_paths_extra_fields_and_overlapping_dates(self):
        malformed = []
        wrong_hash = copy.deepcopy(self.entry)
        wrong_hash["source_sha256"] = "a" * 64
        malformed.append(wrong_hash)
        for path in ("../plan.pdf", "C:/secret.pdf", "/tmp/secret.pdf", "sub\\plan.pdf"):
            bad = copy.deepcopy(self.entry)
            bad["pdf_file"] = path
            malformed.append(bad)
        bad = copy.deepcopy(self.entry)
        bad["assessments"][0]["ocr"] = {"text": "unreviewed extra"}
        malformed.append(bad)
        bad = copy.deepcopy(self.entry)
        bad["groups"][0]["terms"].append(
            {"semester": 8, "start_date": "2027-01-31", "end_date": "2027-06-30"}
        )
        malformed.append(bad)
        for entry in malformed:
            with self.subTest(entry=entry), self.assertRaises(bundle.BundleError):
                self.load([entry])

    def test_official_urls_and_http_credentials_are_restricted(self):
        for url in (
            "http://www.fa.ru/upload/plan.pdf",
            "https://fa.ru.evil.test/upload/a.pdf",
            "https://www.fa.ru/upload/%252e%252e/private.pdf",
            "https://user:pass@fa.ru/upload/a.pdf",
        ):
            with self.subTest(url=url), self.assertRaises(bundle.BundleError):
                bundle.official_url(url)
        for origin in (
            "http://192.168.1.40:9583",
            "https://user:pass@example.test",
            "https://example.test/api",
            "file:///tmp/socket",
        ):
            with self.subTest(origin=origin), self.assertRaises(bundle.BundleError):
                bundle.validate_base_url(origin)
        for origin in ("http://127.0.0.1:9583", "http://[::1]:9583", "https://example.test"):
            self.assertEqual(bundle.validate_base_url(origin), origin)

    def test_default_dry_run_reads_all_details_and_never_mutates(self):
        client = FakeClient([self.published(groups=[self.group])])
        result = bundle.publish_bundle(self.load(), client, self.output)
        self.assertEqual(result["mode"], "dry_run")
        self.assertTrue(all(method == "GET" for method, _ in client.calls))
        self.assertIn(("GET", "/api/curricula/1"), client.calls)
        self.assertEqual(list(self.root.glob("*.before-*.json")), [])

    def test_apply_creates_publishes_verifies_and_second_run_is_read_only(self):
        def backup_exists_before_write():
            backups = list(self.root.glob("*.before-*.json"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(json.loads(backups[0].read_text())["documents"], [])

        client = FakeClient(first_write=backup_exists_before_write)
        documents = self.load()
        result = bundle.publish_bundle(
            documents, client, self.output, apply=True, progress=lambda _: None
        )
        self.assertEqual(result["status"], "complete")
        self.assertEqual(client.documents[1]["published_assessments"], [self.row])
        self.assertEqual(client.documents[1]["groups"], [self.group])
        self.assertEqual(client.calls[-1], ("GET", "/api/curricula/1"))
        client.calls.clear()
        repeated = bundle.publish_bundle(
            documents, client, self.output, apply=True, progress=lambda _: None
        )
        self.assertEqual(repeated["status"], "complete")
        self.assertTrue(all(method == "GET" for method, _ in client.calls))

    def test_merge_preserves_other_groups_and_refuses_changed_existing_dates(self):
        other = {**self.group, "group_id": "other-group", "group_name": "Other group"}
        client = FakeClient([self.published(groups=[other])])
        bundle.publish_bundle(self.load(), client, self.output, apply=True, progress=lambda _: None)
        self.assertEqual(
            {group["group_id"] for group in client.documents[1]["groups"]},
            {"162426", "other-group"},
        )
        changed = copy.deepcopy(self.group)
        changed["terms"][0]["end_date"] = "2027-02-01"
        with self.assertRaises(bundle.BundleError):
            bundle.merged_groups([self.group], [changed])

    def test_other_document_ownership_conflicts_before_any_batch_mutation(self):
        other = self.published(groups=[self.group])
        other["source_url"] = "https://www.fa.ru/upload/other.pdf"
        client = FakeClient([other])
        with self.assertRaisesRegex(bundle.BundleError, "another document"):
            bundle.publish_bundle(self.load(), client, self.output, apply=True)
        self.assertTrue(all(method == "GET" for method, _ in client.calls))

    def test_conflicting_publication_in_second_plan_prevents_first_creation(self):
        second = copy.deepcopy(self.entry)
        second["metadata"]["source_url"] = "https://www.fa.ru/upload/second.pdf"
        second["groups"] = []
        existing = self.published()
        existing["source_url"] = second["metadata"]["source_url"]
        existing["published_hash"] = "f" * 64
        client = FakeClient([existing])
        with self.assertRaisesRegex(bundle.BundleError, "published PDF"):
            bundle.publish_bundle(self.load([self.entry, second]), client, self.output, apply=True)
        self.assertTrue(all(method == "GET" for method, _ in client.calls))

    def test_conflicting_published_records_refuse_overwrite(self):
        existing = self.published()
        existing["published_assessments"] = [{**self.row, "kind": "pass"}]
        client = FakeClient([existing])
        with self.assertRaisesRegex(bundle.BundleError, "published assessments"):
            bundle.publish_bundle(self.load(), client, self.output, apply=True)
        self.assertTrue(all(method == "GET" for method, _ in client.calls))

    def supplement(self):
        child = copy.deepcopy(self.entry)
        child["metadata"].update(
            title="Supporting assessment document", source_url="https://www.fa.ru/upload/brs.pdf"
        )
        child["groups"] = []
        child["parent_source_url"] = self.metadata["source_url"]
        return child

    def test_supplement_is_created_after_root_and_repeated_without_writes(self):
        child = self.supplement()
        # Input order must not make the child refer to an as-yet missing ID.
        documents = self.load([child, self.entry])
        self.assertEqual(documents[0]["metadata"]["source_url"], self.metadata["source_url"])
        client = FakeClient()
        dry_run = bundle.publish_bundle(documents, client, self.output)
        self.assertEqual(dry_run["documents"][1]["parent_source_url"], self.metadata["source_url"])
        self.assertTrue(all(method == "GET" for method, _ in client.calls))
        result = bundle.publish_bundle(
            documents, client, self.output, apply=True, progress=lambda _: None
        )
        self.assertIsNone(client.documents[1]["parent_document_id"])
        self.assertEqual(client.documents[2]["parent_document_id"], 1)
        self.assertEqual(client.documents[1]["groups"], [self.group])
        self.assertEqual(client.documents[2]["groups"], [])
        self.assertEqual(result["documents"][1]["parent_document_id"], 1)
        client.calls.clear()
        bundle.publish_bundle(documents, client, self.output, apply=True, progress=lambda _: None)
        self.assertTrue(all(method == "GET" for method, _ in client.calls))

    def test_supplement_rejects_missing_self_nested_and_cyclic_parents_locally(self):
        child = self.supplement()
        with self.assertRaisesRegex(bundle.BundleError, "another root"):
            self.load([child])
        self_parent = copy.deepcopy(child)
        self_parent["parent_source_url"] = self_parent["metadata"]["source_url"]
        with self.assertRaisesRegex(bundle.BundleError, "another root"):
            self.load([self.entry, self_parent])
        nested = copy.deepcopy(child)
        nested["metadata"]["source_url"] = "https://www.fa.ru/upload/nested.pdf"
        nested["parent_source_url"] = child["metadata"]["source_url"]
        with self.assertRaisesRegex(bundle.BundleError, "chains and cycles"):
            self.load([self.entry, child, nested])
        root_cycle = copy.deepcopy(self.entry)
        root_cycle["groups"] = []
        root_cycle["parent_source_url"] = child["metadata"]["source_url"]
        with self.assertRaisesRegex(bundle.BundleError, "chains and cycles"):
            self.load([root_cycle, child])

    def test_supplement_rejects_direct_groups_and_different_cohort(self):
        child = self.supplement()
        child["groups"] = [{**self.group, "group_id": "extra-group"}]
        with self.assertRaisesRegex(bundle.BundleError, "cannot own group"):
            self.load([self.entry, child])
        child = self.supplement()
        child["metadata"]["admission_year"] = 2025
        with self.assertRaisesRegex(bundle.BundleError, "cohort metadata"):
            self.load([self.entry, child])

    def test_existing_supplement_parent_conflict_prevents_all_writes(self):
        child = self.supplement()
        registered_child = {
            **self.published(identifier=2),
            **child["metadata"],
            "parent_document_id": 99,
        }
        client = FakeClient([self.published(), registered_child])
        with self.assertRaisesRegex(bundle.BundleError, "parent conflicts"):
            bundle.publish_bundle(self.load([self.entry, child]), client, self.output, apply=True)
        self.assertTrue(all(method == "GET" for method, _ in client.calls))

    def test_input_replacement_is_detected_before_first_write(self):
        documents = self.load()
        (self.root / "plan.pdf").write_bytes(b"%PDF-changed")
        client = FakeClient()
        with self.assertRaisesRegex(bundle.BundleError, "SHA256"):
            bundle.publish_bundle(documents, client, self.output, apply=True)
        self.assertTrue(all(method == "GET" for method, _ in client.calls))
        self.assertEqual(json.loads(self.output.read_text())["status"], "failed")

    def test_incorrect_persisted_binding_is_not_reported_as_success(self):
        class ForgetfulClient(FakeClient):
            def request(self, method, path, **kwargs):
                if method == "PUT" and path.endswith("/groups"):
                    self.calls.append((method, path))
                    return self.documents[1]
                return super().request(method, path, **kwargs)

        client = ForgetfulClient([self.published()])
        with self.assertRaisesRegex(bundle.BundleError, "verification failed"):
            bundle.publish_bundle(
                self.load(), client, self.output, apply=True, progress=lambda _: None
            )
        self.assertEqual(json.loads(self.output.read_text())["status"], "failed")

    def test_polling_logs_only_state_changes_and_respects_deadline(self):
        client = FakeClient([self.published()])
        client.documents[1]["processing_state"] = "queued"
        now, messages = [0], []

        def sleep(seconds):
            now[0] += seconds

        with self.assertRaisesRegex(bundle.BundleError, "deadline"):
            bundle.wait_ready(
                client,
                1,
                wait_seconds=11,
                clock=lambda: now[0],
                sleep=sleep,
                progress=messages.append,
            )
        self.assertEqual(now[0], 11)
        self.assertEqual(messages, ["Document 1: queued"])

    def test_transport_never_logs_error_body_and_does_not_follow_redirects(self):
        opener = unittest.mock.Mock()
        opener.open.side_effect = HTTPError(
            "http://127.0.0.1",
            403,
            "secret error",
            {},
            io.BytesIO(b"password=secret bearer=hidden"),
        )
        with patch.object(bundle, "build_opener", return_value=opener):
            with self.assertRaises(bundle.BundleError) as error:
                bundle.AdminClient("http://127.0.0.1:9583", "private-user", "private-password")
        self.assertEqual(str(error.exception), "API request failed: HTTP 403")
        with self.assertRaisesRegex(bundle.BundleError, "redirects"):
            bundle._NoRedirect().redirect_request(None, None, 302, "", {}, "https://attacker.test")


if __name__ == "__main__":
    unittest.main()

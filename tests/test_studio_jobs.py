import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-unit-tests")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_stats_app.routers import studio_jobs_router as jobs


class TestStudioJobs(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(jobs.router, prefix="/api")
        self.db = AsyncMock()
        self.app.dependency_overrides[jobs.get_current_user] = lambda: {
            "id": 7,
            "username": "student",
        }
        self.app.dependency_overrides[jobs.get_db_session_dependency] = lambda: self.db
        self.client = TestClient(self.app)
        self.redis = AsyncMock()
        for target, value in (
            ("redis_client", SimpleNamespace(client=self.redis)),
            ("enforce_rate_limit", AsyncMock()),
            ("record_product_event", AsyncMock()),
        ):
            patcher = patch.object(jobs, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_enqueue_persists_owner_before_dispatch_and_does_not_wait_for_result(self):
        def publish(task, *args, **kwargs):
            self.redis.set.assert_awaited_once()
            metadata = json.loads(self.redis.set.await_args.args[1])
            self.assertEqual(metadata["owner_id"], 7)
            self.assertEqual(kwargs["_task_id"], metadata["job_id"])
            self.assertEqual(args, ("# Notes", "Document", "student", "Today"))
            return Mock()

        with patch.object(jobs, "dispatch_traced_task", side_effect=publish) as dispatch:
            response = self.client.post(
                "/api/studio/jobs", json={"type": "markdown", "content": "# Notes"}
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "queued")
        dispatch.assert_called_once()

    def test_cannot_publish_if_owner_metadata_cannot_be_stored(self):
        self.redis.set.side_effect = ConnectionError("private redis url")
        with patch.object(jobs, "dispatch_traced_task") as dispatch:
            response = self.client.post(
                "/api/studio/jobs", json={"type": "latex", "content": "text"}
            )
        self.assertEqual(response.status_code, 503)
        dispatch.assert_not_called()
        self.assertNotIn("private redis", response.text)

    def test_foreign_and_expired_jobs_are_indistinguishable(self):
        job_id = str(uuid4())
        with patch.object(jobs, "_task_status") as result:
            for metadata in [None, json.dumps({"owner_id": 8})]:
                self.redis.get.return_value = metadata
                response = self.client.get(f"/api/studio/jobs/{job_id}")
                self.assertEqual(response.status_code, 404)
        result.assert_not_called()

    def test_result_survives_a_new_http_client_and_deduplicates_analytics(self):
        job_id = str(uuid4())
        self.redis.get.return_value = json.dumps(
            {"owner_id": 7, "expires_at": "2099-01-01T00:00:00Z"}
        )
        with patch.object(
            jobs, "_task_status", return_value=("success", {"status": "success", "pdf": "JVBERg=="})
        ):
            for client in [self.client, TestClient(self.app)]:
                response = client.get(f"/api/studio/jobs/{job_id}")
                self.assertEqual(response.json()["result"]["pdf"], "JVBERg==")
                self.assertEqual(response.headers["cache-control"], "no-store")
        calls = jobs.record_product_event.await_args_list
        self.assertEqual(calls[0].kwargs["dedupe_key"], calls[1].kwargs["dedupe_key"])

    def test_cancellation_is_owner_scoped_and_waits_for_worker(self):
        job_id = str(uuid4())
        self.redis.get.return_value = json.dumps({"owner_id": 8})
        response = self.client.post(f"/api/studio/jobs/{job_id}/cancel")
        self.assertEqual(response.status_code, 404)
        self.redis.set.assert_not_awaited()
        self.redis.get.return_value = json.dumps({"owner_id": 7, "expires_at": "2099-01-01"})
        with (
            patch.object(jobs, "_task_status", return_value=("running", None)),
            patch.object(jobs.celery_app.control, "revoke") as revoke,
        ):
            response = self.client.post(f"/api/studio/jobs/{job_id}/cancel")
        self.assertEqual(response.json()["status"], "cancelling")
        self.assertEqual(self.redis.set.await_args_list[0].args[0], jobs.CANCEL_PREFIX + job_id)
        revoke.assert_not_called()
        task = SimpleNamespace(state="SUCCESS", result={"status": "cancelled"})
        with patch.object(jobs.celery_app, "AsyncResult", return_value=task):
            self.assertEqual(jobs._task_status(job_id), ("cancelled", None))

    def test_completed_job_is_not_cancelled_and_storage_failure_is_not_success(self):
        job_id = str(uuid4())
        self.redis.get.return_value = json.dumps({"owner_id": 7})
        with patch.object(jobs, "_task_status", return_value=("success", {})):
            self.assertEqual(
                self.client.post(f"/api/studio/jobs/{job_id}/cancel").json()["status"], "success"
            )
        self.redis.set.assert_not_awaited()
        self.redis.set.side_effect = ConnectionError("private endpoint")
        with patch.object(jobs, "_task_status", return_value=("running", None)):
            response = self.client.post(f"/api/studio/jobs/{job_id}/cancel")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private endpoint", response.text)

    def test_types_and_payloads_are_validated(self):
        for payload in [{"type": "shell", "content": "ls"}, {"type": "latex", "content": ""}]:
            response = self.client.post("/api/studio/jobs", json=payload)
            self.assertEqual(response.status_code, 422)
        self.redis.set.assert_not_awaited()

    def test_project_jobs_enforce_ownership(self):
        from fastapi import HTTPException

        with patch.object(
            jobs, "get_owned_project_or_404", AsyncMock(side_effect=HTTPException(404, "Not found"))
        ):
            response = self.client.post("/api/studio/projects/13/jobs")
        self.assertEqual(response.status_code, 404)
        self.redis.set.assert_not_awaited()

    def test_worker_errors_are_generic_and_build_cache_is_not_returned(self):
        task = SimpleNamespace(state="FAILURE", result=Exception("secret connection URL"))
        with patch.object(jobs.celery_app, "AsyncResult", return_value=task):
            status, result = jobs._task_status(str(uuid4()))
            self.assertEqual(status, "error")
            self.assertNotIn("secret", str(result))
            task.state, task.result = (
                "SUCCESS",
                {"status": "success", "pdf": "PDF", "build_cache": "PRIVATE CACHE"},
            )
            status, result = jobs._task_status(str(uuid4()))
            self.assertEqual(status, "success")
            self.redis.get.return_value = json.dumps({"owner_id": 7, "expires_at": "2099-01-01"})
            response = self.client.get(f"/api/studio/jobs/{uuid4()}")
            self.assertEqual(response.json()["result"], {"status": "success", "pdf": "PDF"})

    def test_project_job_dispatches_the_project_format(self):
        for kind, task in [("markdown", jobs.render_pdf_task), ("mermaid", jobs.render_mermaid)]:
            project = SimpleNamespace(project_type=kind, name="Notes", build_cache=None)
            file = SimpleNamespace(
                file_path="main.txt", is_main=True, content_binary=None, content_text="source"
            )
            self.db.execute.return_value = Mock(
                scalars=Mock(return_value=Mock(all=Mock(return_value=[file])))
            )
            with (
                patch.object(jobs, "get_owned_project_or_404", AsyncMock(return_value=project)),
                patch.object(jobs, "dispatch_traced_task") as dispatch,
            ):
                response = self.client.post("/api/studio/projects/13/jobs")
            self.assertEqual(response.status_code, 202)
            self.assertIs(dispatch.call_args.args[0], task)
            self.assertEqual(dispatch.call_args.args[1], "source")


class TestBuildCache(unittest.IsolatedAsyncioTestCase):
    async def test_cache_persists_only_for_the_matching_source_snapshot(self):
        file = SimpleNamespace(
            file_path="main.tex", is_main=True, content_binary=None, content_text="source"
        )
        metadata = {
            "project_id": 13,
            "owner_id": 7,
            "source_fingerprint": jobs._project_snapshot([file])[2],
        }
        db = AsyncMock()
        db.execute.return_value = Mock(
            scalars=Mock(return_value=Mock(all=Mock(return_value=[file])))
        )
        await jobs._save_build_cache(db, metadata, "Y2FjaGU=")
        db.commit.assert_awaited_once()
        query = db.execute.await_args.args[0]
        self.assertEqual(query.compile().params["build_cache"], b"cache")
        db.reset_mock()
        file.content_text = "new source after job submission"
        await jobs._save_build_cache(db, metadata, "Y2FjaGU=")
        db.commit.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

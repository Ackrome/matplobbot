import unittest

FASTAPI_AVAILABLE = True
try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from fastapi_stats_app.middleware import CorrelationIdMiddleware
    from shared_lib.request_context import get_correlation_id
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class TestCorrelationIdMiddleware(unittest.TestCase):
    def test_generates_and_returns_request_id_header(self):
        app = FastAPI()
        app.add_middleware(CorrelationIdMiddleware)

        @app.get("/ping")
        async def ping():
            return {"cid": get_correlation_id()}

        client = TestClient(app)
        response = client.get("/ping")

        self.assertEqual(response.status_code, 200)
        header_cid = response.headers.get("X-Request-ID")
        self.assertIsNotNone(header_cid)
        self.assertEqual(response.json()["cid"], header_cid)

    def test_respects_incoming_request_id_header(self):
        app = FastAPI()
        app.add_middleware(CorrelationIdMiddleware)

        @app.get("/ping")
        async def ping():
            return {"cid": get_correlation_id()}

        client = TestClient(app)
        response = client.get("/ping", headers={"X-Request-ID": "external-cid-123"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Request-ID"), "external-cid-123")
        self.assertEqual(response.json()["cid"], "external-cid-123")

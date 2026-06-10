import os
import unittest

FASTAPI_AVAILABLE = True
try:
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-unit-tests")

    from fastapi import Depends, FastAPI, Query
    from fastapi.testclient import TestClient

    from fastapi_stats_app import auth as fastapi_auth  # noqa: E402
    from fastapi_stats_app.openapi_docs import configure_openapi  # noqa: E402
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class TestOpenApiDocs(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI(
            title="Matplobbot API",
            version="0.1.0",
            docs_url=None,
            redoc_url=None,
        )

        @self.app.get("/protected")
        async def protected(_user: dict = Depends(fastapi_auth.get_current_user)):
            return {"status": "ok"}

        @self.app.get("/api/schedule/search", tags=["schedule"])
        async def schedule_search(term: str = Query(...)):
            return [{"id": "group-1", "label": term, "type": "group"}]

        configure_openapi(self.app)
        self.client = TestClient(self.app)

    def test_docs_html_includes_custom_assets(self):
        response = self.client.get("/docs")

        self.assertEqual(response.status_code, 200)
        self.assertIn("/static/css/swagger-theme.css?v=2", response.text)
        self.assertIn("/static/js/swagger-branding.js?v=1", response.text)
        self.assertIn("Matplobbot API Docs", response.text)
        self.assertIn("/static/img/matplobbot-mark.svg", response.text)
        self.assertIn('class="mpb-swagger-docs"', response.text)

    def test_redoc_html_includes_custom_assets(self):
        response = self.client.get("/redoc")

        self.assertEqual(response.status_code, 200)
        self.assertIn("/static/css/swagger-theme.css?v=2", response.text)
        self.assertIn("Matplobbot API ReDoc", response.text)
        self.assertIn("/static/img/matplobbot-mark.svg", response.text)
        self.assertIn('class="mpb-redoc-docs"', response.text)
        self.assertIn('spec-url="/openapi.json"', response.text)

    def test_openapi_schema_includes_auth_instructions_and_logo(self):
        schema = self.app.openapi()

        self.assertEqual(
            schema["info"]["summary"], "Schedule, stats, studio, and calendar APIs for Matplobbot."
        )
        self.assertIn("Username/password flow", schema["info"]["description"])
        self.assertIn("Telegram flow", schema["info"]["description"])
        self.assertEqual(schema["info"]["x-logo"]["url"], "/static/img/matplobbot-mark.svg")

        security_scheme = schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]
        self.assertIn("/api/auth/login", security_scheme["description"])
        self.assertIn("/api/auth/telegram", security_scheme["description"])

    def test_openapi_schema_adds_markdown_and_common_response_schemas(self):
        schema = self.app.openapi()

        self.assertIn("ErrorResponse", schema["components"]["schemas"])
        self.assertIn("ValidationErrorResponse", schema["components"]["schemas"])
        self.assertIn(
            {"name": "Website API", "tags": ["auth", "schedule", "studio", "calendar"]},
            schema["x-tagGroups"],
        )

        protected_responses = schema["paths"]["/protected"]["get"]["responses"]
        self.assertEqual(
            protected_responses["401"]["content"]["application/json"]["schema"]["$ref"],
            "#/components/schemas/ErrorResponse",
        )
        self.assertEqual(
            protected_responses["403"]["content"]["application/json"]["schema"]["$ref"],
            "#/components/schemas/ErrorResponse",
        )
        self.assertEqual(
            protected_responses["500"]["content"]["application/json"]["schema"]["$ref"],
            "#/components/schemas/ErrorResponse",
        )

        search_operation = schema["paths"]["/api/schedule/search"]["get"]
        self.assertIn("### Schedule behavior", search_operation["description"])
        self.assertIn("### Response semantics", search_operation["description"])
        self.assertEqual(
            search_operation["responses"]["422"]["content"]["application/json"]["schema"]["$ref"],
            "#/components/schemas/ValidationErrorResponse",
        )
        self.assertEqual(
            search_operation["responses"]["429"]["content"]["application/json"]["schema"]["$ref"],
            "#/components/schemas/ErrorResponse",
        )
        self.assertIn("Retry-After", search_operation["responses"]["429"]["headers"])

from copy import deepcopy

from fastapi import FastAPI
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse

from .config import PUBLIC_API_URL

DOCS_CSS_URL = "/static/css/swagger-theme.css?v=2"
DOCS_JS_URL = "/static/js/swagger-branding.js?v=1"
DOCS_FAVICON_URL = "/static/img/matplobbot-mark.svg"

OPENAPI_SUMMARY = "Schedule, stats, studio, and calendar APIs for Matplobbot."
OPENAPI_DESCRIPTION = """
Matplobbot exposes authenticated website APIs, admin stats endpoints, Studio document flows,
schedule search/data routes, and secret-based calendar feeds from one FastAPI service.

## Authentication

Most `/api/*` routes require a bearer token.

### Username/password flow

1. Create an account with `POST /api/auth/register`.
2. Click **Authorize** in Swagger UI and sign in with the same username/password.
3. Swagger UI will call `POST /api/auth/login` and attach the returned bearer token automatically.

### Telegram flow

1. Exchange Telegram Login Widget payload data through `POST /api/auth/telegram`.
2. Copy the returned `access_token`.
3. Click **Authorize** and paste the token value when you want to test protected routes manually.

### Notes

- Public iCal feed routes under `/api/cal/{secret}*` are intentionally tokenless and rely on the secret URL.
- Admin-only routes require an authenticated account whose resolved role is `admin`.
- Protected HTML pages are excluded from this schema so `/docs` stays API-focused.
"""

OPENAPI_TAGS = [
    {
        "name": "auth",
        "description": "Account registration, password login, Telegram login, and user preferences.",
    },
    {
        "name": "schedule",
        "description": "Schedule entity search, cached entities, and schedule window loading.",
    },
    {
        "name": "stats",
        "description": "Admin analytics, exports, outreach tools, and health checks.",
    },
    {
        "name": "studio",
        "description": "Document Studio project management, compile flows, assets, and Telegram delivery.",
    },
    {
        "name": "calendar",
        "description": "Website calendar profile management plus secret-backed iCal feeds.",
    },
    {
        "name": "websockets",
        "description": "Authenticated websocket streams used by the admin dashboard.",
    },
]

SWAGGER_UI_PARAMETERS = {
    "deepLinking": True,
    "displayRequestDuration": True,
    "defaultModelsExpandDepth": 2,
    "docExpansion": "list",
    "filter": True,
    "persistAuthorization": True,
    "syntaxHighlight": {"theme": "obsidian"},
}

ERROR_RESPONSE_SCHEMA = {
    "title": "ErrorResponse",
    "type": "object",
    "required": ["detail"],
    "properties": {
        "detail": {
            "title": "Detail",
            "description": "Human-readable error detail, or a structured detail object for complex failures.",
            "anyOf": [
                {"type": "string"},
                {"type": "object", "additionalProperties": True},
                {"type": "array", "items": {}},
            ],
        }
    },
}
VALIDATION_ERROR_RESPONSE_SCHEMA = {
    "title": "ValidationErrorResponse",
    "type": "object",
    "required": ["detail"],
    "properties": {
        "detail": {
            "title": "Validation Details",
            "type": "array",
            "items": {
                "type": "object",
                "required": ["loc", "msg", "type"],
                "properties": {
                    "loc": {
                        "type": "array",
                        "items": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
                    },
                    "msg": {"type": "string"},
                    "type": {"type": "string"},
                    "input": {},
                },
            },
        }
    },
}

OPERATION_MARKDOWN_BY_TAG = {
    "auth": """
### Authentication notes

- Public login endpoints return JWT bearer tokens for the website and Swagger UI.
- Protected auth endpoints require the `OAuth2PasswordBearer` token from `Authorize`.
- Telegram login endpoints validate Telegram-signed payloads before creating or reusing a website account.
""",
    "schedule": """
### Schedule behavior

- Search endpoints may blend live RUZ results with local cache fallback results.
- Schedule data responses include offline flags and loaded date bounds so clients can label degraded data.
- Invalid query values return typed validation errors in the `422` response schema.
""",
    "stats": """
### Admin analytics behavior

- Most stats endpoints are admin-only and require a bearer token for an admin website account.
- Export routes can return JSON, CSV, or PDF depending on query parameters.
- Responses include correlation ids where an action is audited or traceable.
""",
    "studio": """
### Studio behavior

- Project endpoints operate on the authenticated user's own Studio files.
- Compile endpoints dispatch worker jobs and can return rendered PDF, PNG, HTML, or structured compile errors.
- Binary download routes document their concrete media types separately from JSON responses.
""",
    "calendar": """
### Calendar behavior

- Authorized subscription endpoints manage website-owned iCal profiles.
- Public feed endpoints are tokenless by design and rely on unguessable secret URLs.
- Feed responses include cache headers and use `text/calendar` content schemas.
""",
    "websockets": """
### WebSocket behavior

- WebSocket routes are documented for discoverability, but interactive testing happens from the dashboard client.
- Streams are scoped to admin dashboards or the authenticated current user's updates.
""",
}

OPERATION_MARKDOWN_BY_ROUTE = {
    ("get", "/api/schedule/search"): """
### Response semantics

- `is_offline=false` means the entity came from the live university API.
- `is_offline=true` means the entity was served from Matplobbot cache while upstream search was degraded.
- `type` always uses the normalized values `group`, `person`, or `auditorium`, even when an alias was requested.
""",
    ("get", "/api/schedule/data/{type}/{id}"): """
### Response semantics

- `schedule` contains a centered 29-day window around `base_date` or today's date.
- `loaded_bounds` tells the frontend which dates were actually loaded.
- `source_updated_at` is populated when the response came from cached schedule data.
""",
    ("get", "/api/stats/users/{user_id}/export_actions"): """
### Export formats

- `format=json` returns `ExportActionsResponse` unless `download=true` asks for a file response.
- `format=csv` returns `text/csv`.
- `format=weekly_pdf` returns `application/pdf` and is rate-limited because rendering is CPU-intensive.
""",
    ("post", "/api/studio/compile"): """
### Compile result

- Successful LaTeX and Markdown flows usually return a base64 `pdf`.
- Mermaid flows usually return a base64 `image`.
- Worker-reported compile problems are represented with `error` or `errors` fields on `StudioCompileResponse`.
""",
    ("post", "/api/studio/projects/{project_id}/compile"): """
### Compile result

- Uses stored project files and the saved incremental build cache when present.
- A successful response can include a refreshed base64 `build_cache` for future compiles.
- Compile failures use the same structured response shape as ad-hoc compiles.
""",
}

RATE_LIMITED_OPERATIONS = {
    ("get", "/api/schedule/search"),
    ("post", "/api/studio/compile"),
    ("post", "/api/studio/projects/{project_id}/compile"),
    ("post", "/api/studio/projects/{project_id}/send_telegram"),
    ("get", "/api/stats/users/{user_id}/export_actions"),
}


def _build_servers() -> list[dict[str, str]]:
    servers = [{"url": "/", "description": "Current host"}]
    if PUBLIC_API_URL:
        servers.insert(0, {"url": PUBLIC_API_URL, "description": "Configured public API URL"})
    return servers


def _inject_custom_assets(
    html: HTMLResponse,
    *,
    page_class: str,
    include_branding_script: bool = False,
) -> HTMLResponse:
    body = html.body.decode("utf-8")
    body = body.replace(
        "</head>",
        (f'<link rel="stylesheet" type="text/css" href="{DOCS_CSS_URL}" />\n</head>'),
    )
    body = body.replace("<body>", f'<body class="{page_class}">', 1)
    if include_branding_script:
        body = body.replace(
            "</body>",
            f'<script src="{DOCS_JS_URL}" defer></script>\n</body>',
        )
    return HTMLResponse(
        content=body,
        status_code=html.status_code,
        headers={k: v for k, v in html.headers.items() if k.lower() != "content-length"},
    )


def _error_response(description: str, example: object) -> dict:
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                "example": {"detail": example},
            }
        },
    }


def _validation_error_response() -> dict:
    return {
        "description": "Request path, query, header, or body validation failed.",
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ValidationErrorResponse"},
                "example": {
                    "detail": [
                        {
                            "loc": ["query", "base_date"],
                            "msg": "Input should be a valid date",
                            "type": "date_from_datetime_parsing",
                        }
                    ]
                },
            }
        },
    }


def _rate_limit_response() -> dict:
    response = _error_response(
        "The request exceeded the configured Redis-backed rate limit.",
        "Rate limit exceeded. Try again later.",
    )
    response["headers"] = {
        "Retry-After": {
            "description": "Seconds until this client can retry the same rate-limited action.",
            "schema": {"type": "integer", "minimum": 1},
        }
    }
    return response


def _install_common_error_schemas(schema: dict) -> None:
    schemas = schema.setdefault("components", {}).setdefault("schemas", {})
    schemas.setdefault("ErrorResponse", deepcopy(ERROR_RESPONSE_SCHEMA))
    schemas.setdefault(
        "ValidationErrorResponse",
        deepcopy(VALIDATION_ERROR_RESPONSE_SCHEMA),
    )


def _operation_has_bearer_auth(operation: dict) -> bool:
    return bool(operation.get("security"))


def _append_operation_markdown(path: str, method: str, operation: dict) -> None:
    description = str(operation.get("description") or "").strip()
    sections: list[str] = []

    route_section = OPERATION_MARKDOWN_BY_ROUTE.get((method, path))
    if route_section:
        sections.append(route_section.strip())

    tag = next(iter(operation.get("tags") or []), "")
    tag_section = OPERATION_MARKDOWN_BY_TAG.get(tag)
    if tag_section:
        sections.append(tag_section.strip())

    for section in sections:
        if section and section not in description:
            description = f"{description}\n\n{section}".strip()

    if description:
        operation["description"] = description


def _install_common_operation_responses(path: str, method: str, operation: dict) -> None:
    responses = operation.setdefault("responses", {})

    if "422" in responses:
        responses["422"] = _validation_error_response()

    if _operation_has_bearer_auth(operation):
        responses.setdefault(
            "401",
            _error_response(
                "Bearer token is missing, malformed, expired, or otherwise invalid.",
                "Could not validate credentials",
            ),
        )
        responses.setdefault(
            "403",
            _error_response(
                "The authenticated user is valid but not allowed to perform this action.",
                "Admin access required",
            ),
        )

    if "{" in path:
        responses.setdefault(
            "404",
            _error_response(
                "The requested user, project, file, calendar profile, or schedule resource was not found.",
                "Resource not found",
            ),
        )

    if (method, path) in RATE_LIMITED_OPERATIONS:
        responses.setdefault("429", _rate_limit_response())

    responses.setdefault(
        "500",
        _error_response(
            "Unexpected server-side failure. Check the response detail and server correlation logs.",
            "Internal server error",
        ),
    )


def _enrich_operations(schema: dict) -> None:
    for path, path_item in schema.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in {"get", "put", "post", "delete", "patch", "head", "options"}:
                continue
            if not isinstance(operation, dict):
                continue
            normalized_method = method.lower()
            _append_operation_markdown(path, normalized_method, operation)
            _install_common_operation_responses(path, normalized_method, operation)


def _install_redoc_tag_groups(schema: dict) -> None:
    schema["x-tagGroups"] = [
        {"name": "Website API", "tags": ["auth", "schedule", "studio", "calendar"]},
        {"name": "Operations", "tags": ["stats", "websockets"]},
    ]


def build_openapi_schema(app: FastAPI) -> dict:
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        summary=OPENAPI_SUMMARY,
        description=OPENAPI_DESCRIPTION,
        routes=app.routes,
        tags=OPENAPI_TAGS,
        servers=_build_servers(),
    )

    info = schema.setdefault("info", {})
    info["contact"] = {
        "name": "Matplobbot",
        "url": "https://ivantishchenko.ru",
    }
    info["x-logo"] = {
        "url": DOCS_FAVICON_URL,
        "altText": "Matplobbot",
    }

    security_schemes = schema.setdefault("components", {}).get("securitySchemes", {})
    for scheme in security_schemes.values():
        if scheme.get("type") != "oauth2":
            continue
        scheme["description"] = (
            "Swagger UI supports the password flow against `/api/auth/login`. "
            "For Telegram-issued JWTs from `/api/auth/telegram`, reuse the same Authorize dialog "
            "and paste the returned access token."
        )

    _install_common_error_schemas(schema)
    _enrich_operations(schema)
    _install_redoc_tag_groups(schema)

    app.openapi_schema = schema
    return schema


def configure_openapi(app: FastAPI) -> None:
    app.openapi = lambda: build_openapi_schema(app)

    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui_html() -> HTMLResponse:
        html = get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} Docs",
            oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
            swagger_favicon_url=DOCS_FAVICON_URL,
            swagger_ui_parameters=SWAGGER_UI_PARAMETERS,
        )
        return _inject_custom_assets(
            html,
            page_class="mpb-swagger-docs",
            include_branding_script=True,
        )

    @app.get("/redoc", include_in_schema=False)
    async def custom_redoc_html() -> HTMLResponse:
        html = get_redoc_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} ReDoc",
            redoc_favicon_url=DOCS_FAVICON_URL,
            with_google_fonts=False,
        )
        return _inject_custom_assets(html, page_class="mpb-redoc-docs")

    if app.swagger_ui_oauth2_redirect_url:

        @app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
        async def swagger_ui_redirect() -> HTMLResponse:
            return get_swagger_ui_oauth2_redirect_html()

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse

from .config import PUBLIC_API_URL

DOCS_CSS_URL = "/static/css/swagger-theme.css?v=1"
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


def _build_servers() -> list[dict[str, str]]:
    servers = [{"url": "/", "description": "Current host"}]
    if PUBLIC_API_URL:
        servers.insert(0, {"url": PUBLIC_API_URL, "description": "Configured public API URL"})
    return servers


def _inject_custom_assets(html: HTMLResponse) -> HTMLResponse:
    body = html.body.decode("utf-8")
    body = body.replace(
        "</head>",
        (
            f'<link rel="stylesheet" type="text/css" href="{DOCS_CSS_URL}" />\n'
            "</head>"
        ),
    )
    body = body.replace(
        "</body>",
        f'<script src="{DOCS_JS_URL}" defer></script>\n</body>',
    )
    return HTMLResponse(
        content=body,
        status_code=html.status_code,
        headers={k: v for k, v in html.headers.items() if k.lower() != "content-length"},
    )


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
        return _inject_custom_assets(html)

    if app.swagger_ui_oauth2_redirect_url:

        @app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
        async def swagger_ui_redirect() -> HTMLResponse:
            return get_swagger_ui_oauth2_redirect_html()

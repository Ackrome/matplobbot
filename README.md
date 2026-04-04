<div align="center">
  <img src="image/logo/thelogo.png" alt="Matplobbot Logo" width="320">
  <h1>Matplobbot</h1>
  <strong>Telegram bot and web dashboard for browsing study materials, rendering technical content, and tracking usage in real time.</strong>

  <p align="center">
    <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker">
    <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
    <img src="https://img.shields.io/badge/Aiogram-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white" alt="Aiogram">
    <img src="https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL">
  </p>

  <p align="center">
    <img src="https://img.shields.io/github/actions/workflow/status/Ackrome/matplobbot/ci-cd.yml?style=for-the-badge&label=Build&logo=github" alt="Build status">
  </p>

  <h3>Try it on Telegram</h3>
  <p align="center">
    <a href="https://t.me/matplobbot"><img src="https://img.shields.io/badge/STABLE_TELEGRAM_BOT-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white" alt="Stable Telegram bot"></a>
    <a href="https://t.me/test_matplobbot"><img src="https://img.shields.io/badge/DEVELOPMENT_TELEGRAM_BOT-ff8800?style=for-the-badge&logo=telegram&logoColor=white" alt="Development Telegram bot"></a>
  </p>
</div>

## Overview

Matplobbot is a multi-service platform built around a Telegram bot for technical and educational workflows. It combines interactive content browsing, Markdown and document rendering, university schedule tools, background processing, and a live analytics dashboard in one Docker-based stack.

The project currently includes:

1. A Telegram bot built with `aiogram 3`.
2. A scheduler service for notifications and background schedule checks.
3. A FastAPI analytics dashboard with live stats and user drill-down pages.
4. A Celery worker for heavy rendering tasks such as LaTeX, Mermaid, and document conversion.
5. Supporting infrastructure via PostgreSQL, Redis, Docker Compose, and optional frontend/reverse-proxy services.

## Key Features

### Telegram Bot

- Browse `matplobblib` modules and topics interactively with `/matp_all`.
- Search `matplobblib` content with `/matp_search`.
- Browse and search user-linked GitHub repositories with `/lec_all` and `/lec_search`.
- Render LaTeX formulas to PNG with `/latex`.
- Render Mermaid diagrams to PNG with `/mermaid`.
- Convert Markdown into raw Markdown, HTML, or PDF output.
- Save favorites, manage repositories, and configure personal settings from inline menus.
- Use university schedule search, calendar navigation, daily and weekly views, and subscription-based notifications.

### Schedule Tools

- Search schedules by group, teacher, or auditorium.
- Navigate dates through an inline calendar.
- Receive next-day schedule notifications at a chosen time.
- Get update alerts when lessons change, are added, or are cancelled.

### Web Dashboard

- View live usage stats over WebSockets.
- See popular commands, text activity, action-type breakdowns, and activity trends.
- Inspect user-specific pages with paginated history, filtering, and CSV export.
- Stream the bot log into the dashboard for real-time monitoring.

## Screenshots

### Dashboard

<div align="center">
  <img src="image/notes/Dashboard.png" alt="Dashboard overview" width="800">
</div>

### User Details

<div align="center">
  <img src="image/notes/User.png" alt="User details page" width="700">
</div>

### Schedule Flow

<div align="center">
  <img src="image/notes/schedule_en_1.png" alt="Schedule search" width="260">
  <img src="image/notes/schedule_en_2.png" alt="Schedule results" width="260">
  <img src="image/notes/schedule_en_3.png" alt="Schedule day view" width="260">
</div>

<div align="center">
  <img src="image/notes/calendar_screenshot.png" alt="Inline calendar" width="320">
</div>

## Quickstart

### Prerequisites

- Docker
- Docker Compose

### Minimal `.env` example

Create a `.env` file in the project root. This is a minimal example for local startup; your production setup may require additional variables.

```env
BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
ADMIN_USER_IDS=123456789,987654321
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

POSTGRES_USER=user
POSTGRES_PASSWORD=password
POSTGRES_DB=matplobbot_db
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
```

### Run locally

```bash
git clone https://github.com/Ackrome/matplobbot.git
cd matplobbot
docker compose up --build -d
```

### Access services

- Telegram bot: available through Telegram after `BOT_TOKEN` is configured.
- Analytics dashboard: `http://localhost:9583`
- Static site frontend: `http://localhost:8080`
- Scheduler health endpoint: `http://localhost:9584/health` for operational checks

### Stop the stack

```bash
docker compose down
```

To remove named volumes as well:

```bash
docker compose down -v
```

## Popular Commands

| Command | Purpose |
| :--- | :--- |
| `/start` | Start the bot and initialize the main flow |
| `/help` | Show the command/help menu |
| `/schedule` | Search for a schedule by entity |
| `/myschedule` | Show today's schedule for the saved entity |
| `/matp_all` | Browse library content |
| `/matp_search` | Search inside `matplobblib` |
| `/lec_all` | Browse configured GitHub repositories |
| `/lec_search` | Search Markdown files in a linked repository |
| `/latex` | Render a LaTeX expression to PNG |
| `/mermaid` | Render a Mermaid diagram to PNG |
| `/favorites` | Open saved favorites |
| `/settings` | Manage personal preferences and repositories |

## Architecture

### Tech Stack

| Category | Technology |
| :--- | :--- |
| Backend | Python 3.11+ |
| Bot | Aiogram 3 |
| API | FastAPI, Uvicorn |
| Database | PostgreSQL, asyncpg |
| Queue | Celery, Redis |
| Frontend | HTML, CSS, JavaScript, Chart.js |
| Rendering | Pandoc, TeX Live, Mermaid CLI, Puppeteer |
| Deployment | Docker, Docker Compose, Caddy, Nginx |

### Project Structure

```text
.
|-- bot/                  # Telegram bot logic, handlers, services, templates
|-- fastapi_stats_app/    # Dashboard API, static assets, templates, routers
|-- scheduler_app/        # Scheduled jobs and notification service
|-- shared_lib/           # Shared database, schemas, services, tasks, i18n
|-- main_site_frontend/   # Static frontend served by nginx
|-- proxy/                # Proxy-related utilities/config
|-- alembic/              # Database migrations
|-- docker-compose.yml    # Local orchestration
`-- docker-compose.prod.yml
```

### Rendering Flow

```mermaid
sequenceDiagram
    participant User
    participant Bot
    participant Redis as Redis Broker
    participant Worker as Celery Worker
    participant DB as Database

    User->>Bot: Sends /latex \frac{a}{b}
    Bot->>Redis: Enqueues render task
    Bot-->>User: Sends temporary status message
    Redis->>Worker: Delivers task
    Worker->>Worker: Compiles output
    Worker->>Redis: Stores result
    Bot->>Redis: Retrieves result
    Bot->>User: Sends rendered image
    Bot->>DB: Caches result
```

### Architectural Notes

- Shared logic lives in `shared_lib`, including database access, schemas, Redis integration, tasks, and localization.
- Services are separated by responsibility and communicate through PostgreSQL and Redis.
- Heavy rendering work is moved off the bot process to keep interactions responsive.
- The stack is asynchronous end-to-end for API calls, database work, and bot interactions.

## Development Notes

### Database Migrations

Alembic is used for schema changes.

- In Docker Compose, migrations are applied automatically by the `migrator` service during startup.
- Manual Alembic commands are mainly useful during development when you are changing models or preparing a new migration.

```bash
alembic revision --autogenerate -m "Add new table"
alembic upgrade head
```

### Dependency Locking

- `requirements.in` is the editable dependency source file for base bot/worker images.
- `requirements.txt` is the lockfile consumed by Docker builds.
- Regenerate the lockfile after changing `requirements.in`:

```bash
python -m pip install --upgrade pip pip-tools
pip-compile --resolver=backtracking --output-file requirements.txt requirements.in
```

### Auto-Lint (Remote + Local)

`.github/workflows/autolint-autofix.yml` runs on:
- pull requests to `main`
- direct pushes to `main`

It executes `pre-commit --all-files` and pushes auto-fixes back automatically.
To avoid infinite loops, the job skips commits authored by `github-actions[bot]`.
The autofix run is non-blocking: it commits all available automatic fixes even if
some lint issues still require manual refactoring.
Workflow files under `.github/workflows/` are intentionally excluded from auto-fix
commits due GitHub token permission limits for workflow updates.

Local hooks are still optional and useful for faster feedback:

```bash
python -m pip install --upgrade pip pre-commit
pre-commit install
pre-commit run --all-files
```

- Hook config lives in `.pre-commit-config.yaml`.
- Lint/type tool settings live in `pyproject.toml`.

### CI/CD Summary

The repository uses GitHub Actions for CI and image publishing, with Jenkins handling deployment orchestration. The shared library is versioned and published before updated service images are built and deployed.

## Roadmap

- [x] Integrate SQLAlchemy Core instead of raw SQL
- [x] Add semantic search for project materials
- [ ] Add plugin-based support for multiple universities
- [ ] Support voice-driven schedule requests

## Contributing

Contributions are welcome.

1. Fork the repository.
2. Create a feature branch.
3. Commit your changes.
4. Push the branch.
5. Open a pull request.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---
type: Runbook
title: Docker Build Runbook
description: Local Docker build commands for dependency-changing and ordinary rebuilds.
resource: /howto_build.md
tags: [runbook, docker, build, local-development]
status: stable
generated: { by: codex/gpt-5, at: "2026-08-11T00:47:31+03:00" }
sources:
  - id: okf-spec
    resource: https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
    title: Open Knowledge Format v0.2 specification
---

# Docker Build Runbook

# Overview

Use this runbook when rebuilding the local Docker stack. Rebuild the base images only when dependency files or system packages changed; otherwise rebuild the compose services directly.

# Prerequisites

- Docker is installed and running.
- Docker Compose is available as `docker compose`.
- Commands are executed from the repository root.

# Rebuild After Requirement Changes

Run this path after changing Python requirements, worker system dependencies, or base Dockerfiles.

```bash
# 1. Build Base Python
docker build -t matplobbot-base-python:latest -f Dockerfile.base-python .

# 2. Build Base Worker. This is slow once, then reused until system deps change.
docker build -t matplobbot-base-worker:latest -f Dockerfile.base-worker .

# 3. Build and start services.
docker compose up --build -d
```

# Ordinary Service Rebuild

Run this path when application code changed but requirements and base images did not.

```bash
docker compose up --build -d
```

# Maintenance Notes

- Rebuild `matplobbot-base-worker` after changing Mermaid CLI, Puppeteer, Pandoc, TeX Live, or worker-level system packages.
- Use `docker compose down` before rebuilding only when you need to reset container state.
- Use `docker compose down -v` only when removing named volumes is intentional.

# `schedule_freshness_config.py`

## Purpose

Provides one environment-backed freshness policy for interactive schedule reads in both the Web API and Telegram `/myschedule` command. Keeping the values in a shared module prevents the two surfaces from drifting to different cache ages or wait budgets.

## Public API

- `ScheduleFreshnessSettings` stores the refresh switch, cache-age thresholds, wait budgets, upstream timeout, Redis lease TTL, and failure cooldown.
- `ScheduleFreshnessSettings.effective_freshness_seconds` selects the interactive threshold or the rollback-compatible legacy threshold.
- `load_schedule_freshness_settings()` reads and validates the policy from environment variables.

## Usage

```python
from shared_lib.schedule_freshness_config import load_schedule_freshness_settings

settings = load_schedule_freshness_settings()
freshness_seconds = settings.effective_freshness_seconds
```

## Important dependencies and side effects

The module uses only the Python standard library. Loading settings reads the current process environment and does not mutate it or contact external services.

## Maintenance notes

Keep defaults aligned with `.env.example`. Web and Telegram interactive schedule paths must consume this shared object rather than parsing the same environment variables independently. Preserve the legacy freshness value as a rollback path while `SCHEDULE_ON_OPEN_REFRESH_ENABLED` remains supported.

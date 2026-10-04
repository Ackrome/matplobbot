"""Shared environment-backed policy for interactive schedule refreshes."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _read_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _read_int_env(name: str, default: int, *, minimum: int = 1) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        parsed = int(raw_value)
    except ValueError:
        return default
    return max(minimum, parsed)


def _read_float_env(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        parsed = float(raw_value)
    except ValueError:
        return default
    return max(minimum, parsed)


@dataclass(frozen=True, slots=True)
class ScheduleFreshnessSettings:
    """Refresh policy shared by interactive Web and Telegram schedule views."""

    on_open_refresh_enabled: bool
    interactive_freshness_seconds: int
    legacy_freshness_seconds: int
    live_wait_seconds: float
    initial_live_wait_seconds: float
    upstream_timeout_seconds: float
    lock_ttl_seconds: int
    failure_cooldown_seconds: int

    @property
    def effective_freshness_seconds(self) -> int:
        if self.on_open_refresh_enabled:
            return self.interactive_freshness_seconds
        return self.legacy_freshness_seconds


def load_schedule_freshness_settings() -> ScheduleFreshnessSettings:
    """Read the interactive schedule refresh policy from the process environment."""

    return ScheduleFreshnessSettings(
        on_open_refresh_enabled=_read_bool_env("SCHEDULE_ON_OPEN_REFRESH_ENABLED", True),
        interactive_freshness_seconds=_read_int_env(
            "SCHEDULE_INTERACTIVE_FRESHNESS_SECONDS",
            180,
        ),
        legacy_freshness_seconds=_read_int_env(
            "SCHEDULE_LEGACY_FRESHNESS_SECONDS",
            21600,
        ),
        live_wait_seconds=_read_float_env(
            "SCHEDULE_INTERACTIVE_LIVE_WAIT_SECONDS",
            1.5,
            minimum=0.1,
        ),
        initial_live_wait_seconds=_read_float_env(
            "SCHEDULE_INITIAL_LIVE_WAIT_SECONDS",
            8.0,
            minimum=0.1,
        ),
        upstream_timeout_seconds=_read_float_env(
            "SCHEDULE_INTERACTIVE_UPSTREAM_TIMEOUT_SECONDS",
            6.0,
            minimum=0.5,
        ),
        lock_ttl_seconds=_read_int_env("SCHEDULE_REFRESH_LOCK_TTL_SECONDS", 30),
        failure_cooldown_seconds=_read_int_env(
            "SCHEDULE_REFRESH_FAILURE_COOLDOWN_SECONDS",
            30,
        ),
    )

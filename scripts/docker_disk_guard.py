#!/usr/bin/env python3
"""Monitor Docker/containerd disk usage and perform bounded cache cleanup."""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows development environments
    fcntl = None


DEFAULT_WARN_PERCENT = 20.0
DEFAULT_CRITICAL_PERCENT = 10.0
DEFAULT_WARN_GIB = 30.0
DEFAULT_CRITICAL_GIB = 15.0
DEFAULT_IMAGE_AGE = "168h"
DEFAULT_CONTAINER_AGE = "24h"


@dataclass(frozen=True)
class FilesystemUsage:
    path: str
    total_bytes: int
    available_bytes: int

    @property
    def available_gib(self) -> float:
        return self.available_bytes / (1024**3)

    @property
    def used_percent(self) -> float:
        if self.total_bytes <= 0:
            return 100.0
        return (1 - self.available_bytes / self.total_bytes) * 100


@dataclass(frozen=True)
class GuardSnapshot:
    root: FilesystemUsage
    docker: FilesystemUsage
    docker_root: str
    docker_df: str

    def status(
        self, warn_percent: float, critical_percent: float, warn_gib: float, critical_gib: float
    ) -> str:
        if (
            self.root.used_percent >= 100 - critical_percent
            or self.docker.used_percent >= 100 - critical_percent
            or self.root.available_gib <= critical_gib
            or self.docker.available_gib <= critical_gib
        ):
            return "critical"
        if (
            self.root.used_percent >= 100 - warn_percent
            or self.docker.used_percent >= 100 - warn_percent
            or self.root.available_gib <= warn_gib
            or self.docker.available_gib <= warn_gib
        ):
            return "warning"
        return "ok"


def _run(command: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _docker_root() -> str:
    result = _run(["docker", "info", "--format", "{{.DockerRootDir}}"])
    root = result.stdout.strip()
    if not root:
        raise RuntimeError("Docker returned an empty DockerRootDir")
    return root


def _filesystem_usage(path: str) -> FilesystemUsage:
    usage = shutil.disk_usage(path)
    return FilesystemUsage(path=path, total_bytes=usage.total, available_bytes=usage.free)


def _docker_df() -> str:
    result = _run(["docker", "system", "df"], check=False)
    return " ".join((result.stdout or result.stderr).split())[:2000]


def snapshot() -> GuardSnapshot:
    docker_root = _docker_root()
    return GuardSnapshot(
        root=_filesystem_usage("/"),
        docker=_filesystem_usage(docker_root),
        docker_root=docker_root,
        docker_df=_docker_df(),
    )


def _format_snapshot(value: GuardSnapshot, status: str, phase: str) -> dict[str, Any]:
    return {
        "phase": phase,
        "status": status,
        "root": {
            "path": value.root.path,
            "available_gib": round(value.root.available_gib, 2),
            "used_percent": round(value.root.used_percent, 2),
        },
        "docker": {
            "path": value.docker.path,
            "available_gib": round(value.docker.available_gib, 2),
            "used_percent": round(value.docker.used_percent, 2),
        },
        "docker_system_df": value.docker_df,
    }


def _cleanup(profile: str, image_age: str, container_age: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if profile == "runner":
        results.extend(_remove_stale_builders(image_age))

    commands: list[list[str]] = [
        ["docker", "builder", "prune", "--force", "--filter", f"until={image_age}"],
        ["docker", "container", "prune", "--force", "--filter", f"until={container_age}"],
    ]
    if profile == "runner":
        commands.append(
            ["docker", "image", "prune", "--all", "--force", "--filter", f"until={image_age}"]
        )
    else:
        commands.append(["docker", "image", "prune", "--force", "--filter", f"until={image_age}"])

    for command in commands:
        completed = _run(command, check=False)
        output = " ".join((completed.stdout or completed.stderr).split())
        results.append(
            {"command": command[:3], "returncode": completed.returncode, "output": output[:1000]}
        )
        if completed.returncode != 0:
            raise RuntimeError(f"Docker cleanup command failed: {' '.join(command[:3])}")
    return results


def _remove_stale_builders(image_age: str) -> list[dict[str, Any]]:
    """Remove inactive docker-container builders older than the cleanup age."""
    if not image_age.endswith("h"):
        return []
    try:
        age_hours = float(image_age[:-1])
    except ValueError:
        return []
    if age_hours <= 0:
        return []

    listing = _run(["docker", "buildx", "ls", "--format", "{{json .}}"], check=False)
    if listing.returncode != 0:
        return [
            {
                "command": ["docker", "buildx", "ls"],
                "returncode": listing.returncode,
                "output": " ".join(listing.stderr.split())[:1000],
            }
        ]

    cutoff = datetime.now(UTC) - timedelta(hours=age_hours)
    names: set[str] = set()
    for line in listing.stdout.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        name = item.get("Name")
        if (
            item.get("Driver") != "docker-container"
            or item.get("Current")
            or not isinstance(name, str)
            or name.endswith("0")
            or name in names
        ):
            continue
        last_activity = item.get("LastActivity")
        if not isinstance(last_activity, str):
            continue
        try:
            activity_time = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
        except ValueError:
            continue
        if activity_time > cutoff:
            continue
        names.add(name)

    results: list[dict[str, Any]] = []
    for name in sorted(names):
        completed = _run(["docker", "buildx", "rm", name], check=False)
        output = " ".join((completed.stdout or completed.stderr).split())
        results.append(
            {
                "command": ["docker", "buildx", "rm", name],
                "returncode": completed.returncode,
                "output": output[:1000],
            }
        )
    return results


@contextlib.contextmanager
def _guard_lock(path: str):
    handle = open(path, "a+", encoding="utf-8")
    try:
        if fcntl is not None:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("another disk guard invocation is already running") from exc
        yield
    finally:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "cleanup", "monitor"))
    parser.add_argument("--profile", choices=("runner", "production"), default="production")
    parser.add_argument("--warn-percent", type=_positive_float, default=DEFAULT_WARN_PERCENT)
    parser.add_argument(
        "--critical-percent", type=_positive_float, default=DEFAULT_CRITICAL_PERCENT
    )
    parser.add_argument("--warn-gib", type=_positive_float, default=DEFAULT_WARN_GIB)
    parser.add_argument("--critical-gib", type=_positive_float, default=DEFAULT_CRITICAL_GIB)
    parser.add_argument("--image-age", default=DEFAULT_IMAGE_AGE)
    parser.add_argument("--container-age", default=DEFAULT_CONTAINER_AGE)
    parser.add_argument("--lock-file", default="/tmp/matplobbot-docker-disk-guard.lock")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.critical_percent >= args.warn_percent or args.critical_gib >= args.warn_gib:
        raise SystemExit("critical thresholds must be lower than warning thresholds")

    with _guard_lock(args.lock_file):
        before = snapshot()
        status = before.status(
            args.warn_percent, args.critical_percent, args.warn_gib, args.critical_gib
        )
        payload: dict[str, Any] = _format_snapshot(before, status, args.command)

        if args.command == "check" or status == "ok":
            print(json.dumps(payload, ensure_ascii=False))
            return 2 if status == "critical" else 0

        payload["cleanup"] = _cleanup(args.profile, args.image_age, args.container_age)
        after = snapshot()
        after_status = after.status(
            args.warn_percent, args.critical_percent, args.warn_gib, args.critical_gib
        )
        payload["after"] = _format_snapshot(after, after_status, "after-cleanup")
        payload["status"] = after_status
        print(json.dumps(payload, ensure_ascii=False))
        return 2 if after_status == "critical" else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(
            json.dumps({"status": "error", "error": str(exc)[:500]}, ensure_ascii=False),
            file=sys.stderr,
        )
        raise SystemExit(1)

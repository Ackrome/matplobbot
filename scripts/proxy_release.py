"""Deploy or recover the production proxy independently from the application."""

import argparse
import json
import re
import subprocess
import sys
import time

from release_deploy import (
    IMAGE_ID_RE,
    PROXY_ATTEMPT,
    PROXY_STATE,
    STATE,
    ProductionPreflightError,
    check_live_checkout,
    compose,
    maintenance_lock,
    write_private,
)
from release_manifest import run

PROXY_IMAGE = re.compile(r"ghcr\.io/ackrome/matplobbot-proxy@sha256:[0-9a-f]{64}")
SOURCE = "https://github.com/Ackrome/matplobbot"
COMPOSE = ("docker", "compose", "-f", "docker-compose.prod.yml")
EGRESS = "https://api.telegram.org"


def container_id():
    return run(*COMPOSE, "ps", "--all", "-q", "proxy")


def live_image():
    container = container_id()
    if not container or not re.fullmatch(r"[a-f0-9]{12,64}", container):
        raise RuntimeError("Expected exactly one existing proxy container")
    image = run("docker", "inspect", "--format", "{{.Image}}", container)
    if not IMAGE_ID_RE.fullmatch(image):
        raise RuntimeError("Could not identify the running proxy image")
    return image


def read_state(path):
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_candidate(reference, commit):
    """Pull an immutable proxy image and check its source revision and registry digest."""
    if not PROXY_IMAGE.fullmatch(reference) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Expected the published proxy digest and a full source SHA")
    subprocess.run(["docker", "pull", reference], check=True, capture_output=True, timeout=300)
    item = json.loads(run("docker", "image", "inspect", reference))[0]
    labels = item.get("Config", {}).get("Labels") or {}
    image_id = item["Id"]
    if (
        not IMAGE_ID_RE.fullmatch(image_id)
        or reference not in (item.get("RepoDigests") or [])
        or labels.get("org.opencontainers.image.revision") != commit
        or labels.get("org.opencontainers.image.source") != SOURCE
    ):
        raise RuntimeError("The pulled proxy does not match the reviewed digest and source")
    return {"image": reference, "image_id": image_id, "commit": commit}


def wait_healthy(image_id, timeout=240):
    """Require the configured Docker healthcheck and a real SOCKS egress request."""
    deadline = time.monotonic() + timeout
    while (remaining := deadline - time.monotonic()) > 0:
        container = container_id()
        if container:
            facts = run(
                "docker", "inspect", "--format", "{{.Image}} {{.State.Health.Status}}", container
            )
            if facts == f"{image_id} healthy":
                try:
                    check = subprocess.run(
                        [
                            "docker",
                            "exec",
                            container,
                            "curl",
                            "--fail",
                            "--silent",
                            "--output",
                            "/dev/null",
                            "--noproxy",
                            "",
                            "--max-time",
                            "10",
                            "--socks5-hostname",
                            "127.0.0.1:20170",
                            EGRESS,
                        ],
                        capture_output=True,
                        timeout=min(15, remaining),
                        check=False,
                    )
                except subprocess.TimeoutExpired:
                    pass
                else:
                    if check.returncode == 0:
                        return
        time.sleep(min(3, max(0, deadline - time.monotonic())))
    raise RuntimeError("Proxy did not pass readiness and SOCKS egress checks")


def keep(record, slot):
    image_id = record["image_id"]
    if not IMAGE_ID_RE.fullmatch(image_id):
        raise ValueError("Invalid pinned proxy image ID")
    run("docker", "image", "tag", image_id, f"matplobbot-proxy-retained:{slot}")


def switch(record):
    image_id = record["image_id"]
    if not IMAGE_ID_RE.fullmatch(image_id):
        raise ValueError("Invalid pinned proxy image ID")
    override = STATE / "proxy-compose.json"
    write_private(override, {"services": {"proxy": {"image": image_id}}})
    subprocess.run(
        [*compose(override), "up", "-d", "--no-deps", "--no-build", "--pull", "never", "proxy"],
        check=True,
        capture_output=True,
        timeout=120,
    )
    wait_healthy(image_id)


def save_state(state):
    keep(state["current"], "current")
    if state["previous"]:
        keep(state["previous"], "previous")
    write_private(PROXY_STATE, state)


def change(state, candidate):
    """Journal the previous image before touching the proxy and reverse failed starts."""
    current = state["current"]
    keep(current, "rollback")
    keep(candidate, "candidate")
    write_private(PROXY_ATTEMPT, {"before": state})
    try:
        switch(candidate)
        save_state({"current": candidate, "previous": current})
    except Exception:
        try:
            switch(current)
            save_state(state)
        except Exception:
            raise RuntimeError(
                "Proxy rollout and recovery failed. The recovery record was kept"
            ) from None
        PROXY_ATTEMPT.unlink()
        raise RuntimeError(
            "Proxy rollout failed. The previous image passed recovery checks"
        ) from None
    PROXY_ATTEMPT.unlink()


def current_state():
    image_id = live_image()
    state = {"current": {"image_id": image_id, "image": None, "commit": None}, "previous": None}
    if PROXY_STATE.exists():
        state = read_state(PROXY_STATE)
        if state["current"]["image_id"] != image_id:
            raise RuntimeError("The running proxy differs from the independent release record")
    return state


def apply(reference, commit):
    check_live_checkout()
    state = current_state()
    candidate = resolve_candidate(reference, commit)
    if candidate["image_id"] == state["current"]["image_id"]:
        wait_healthy(candidate["image_id"])
        save_state({**state, "current": candidate})
        return
    change(state, candidate)


def rollback():
    check_live_checkout(allow_proxy_recovery=True)
    if PROXY_ATTEMPT.exists():
        state = read_state(PROXY_ATTEMPT)["before"]
        switch(state["current"])
        save_state(state)
        PROXY_ATTEMPT.unlink()
        return
    state = current_state()
    if not state["previous"]:
        raise RuntimeError("There is no previous independently recorded proxy release")
    change(state, state["previous"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    release = sub.add_parser("apply")
    release.add_argument("--image", required=True)
    release.add_argument("--commit", required=True)
    sub.add_parser("rollback")
    args = parser.parse_args()
    try:
        with maintenance_lock():
            if args.command == "apply":
                apply(args.image, args.commit)
            else:
                rollback()
    except (ProductionPreflightError, RuntimeError, ValueError) as exc:
        print(f"Proxy release failed: {exc}", file=sys.stderr)
        return 1
    except (OSError, KeyError, subprocess.SubprocessError):
        print(
            "Proxy release failed while reading deployment state or running Docker", file=sys.stderr
        )
        return 1
    print("Proxy passed readiness and SOCKS egress checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Select and verify an immutable worker AppArmor policy for the Docker daemon."""

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

POLICY_TEMPLATE = Path("security/worker-apparmor.template")
PROFILE_DIRECTORY = Path("/etc/apparmor.d")
LOADED_PROFILES = Path("/sys/kernel/security/apparmor/profiles")
PROFILE_PREFIX = "matplobbot-render-"
NAME_PLACEHOLDER = b"@PROFILE_NAME@"


def _policy(root):
    template = (Path(root) / POLICY_TEMPLATE).read_bytes()
    if template.count(NAME_PLACEHOLDER) != 1:
        raise ValueError("Worker policy must contain exactly one profile-name placeholder")
    name = PROFILE_PREFIX + hashlib.sha256(template).hexdigest()[:24]
    return name, template.replace(NAME_PLACEHOLDER, name.encode("ascii"))


def profile_name(root):
    """Return a name that changes whenever any policy-template byte changes."""
    return _policy(root)[0]


def profile_text(root):
    """Return the exact UTF-8 profile source that a root operator must install."""
    return _policy(root)[1].decode("utf-8")


def docker_uses_apparmor():
    """Query the Docker daemon; the client may be Windows or a remote host."""
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{json .SecurityOptions}}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        options = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise RuntimeError("Cannot establish Docker daemon security capabilities") from exc
    if not isinstance(options, list) or not all(isinstance(value, str) for value in options):
        raise RuntimeError("Docker daemon returned invalid security capabilities")
    return any(value.split(",", 1)[0] == "name=apparmor" for value in options)


def _loaded(name):
    try:
        profiles = LOADED_PROFILES.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(
            "Cannot verify loaded worker AppArmor policy on the daemon host"
        ) from exc
    # flags=(unconfined) grants only this named workload the documented Ubuntu
    # userns exception. Complain-mode profiles are not accepted as installed proof.
    return f"{name} (unconfined)" in profiles


def verify_installed_profile(name, text):
    """Verify retained policy bytes without requiring the candidate checkout.

    A normal Docker-group user cannot read AppArmor's loaded-profile list. The
    caller must also run a disposable container with this named policy before
    maintenance; its positive sandbox compile proves the policy is loaded.
    """
    if not re.fullmatch(PROFILE_PREFIX + r"[0-9a-f]{24}", name):
        raise ValueError("Invalid worker AppArmor profile name")
    content = text.encode("utf-8")
    if content.count(name.encode("ascii")) != 1:
        raise ValueError("Worker AppArmor profile has an invalid identity")
    template = content.replace(name.encode("ascii"), NAME_PLACEHOLDER)
    if name != PROFILE_PREFIX + hashlib.sha256(template).hexdigest()[:24]:
        raise ValueError("Worker AppArmor profile content does not match its name")
    installed = PROFILE_DIRECTORY / name
    try:
        if installed.is_symlink() or installed.read_bytes() != content:
            raise RuntimeError("Installed worker AppArmor policy differs from release source")
        metadata = installed.stat()
        if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) & 0o022:
            raise RuntimeError("Installed worker AppArmor policy must be protected and root-owned")
    except OSError as exc:
        raise RuntimeError(
            f"Worker AppArmor policy {name} must be provisioned on the Docker daemon host"
        ) from exc


def apparmor_security_option(root):
    """Fail closed on AppArmor hosts; preserve Desktop daemons without AppArmor."""
    if not docker_uses_apparmor():
        return None
    name, content = _policy(root)
    verify_installed_profile(name, content.decode("utf-8"))
    return "apparmor=" + name


def install_policy(root):
    """Root-only, add-only provisioning of a content-addressed persistent policy.

    An existing different file is never replaced. Existing loaded policy is never
    reloaded, so provisioning a candidate cannot change a live worker's policy.
    Old profile files remain available for rollback and automatic reboot loading.
    """
    if sys.platform != "linux" or os.geteuid() != 0:
        raise RuntimeError("Worker AppArmor policy provisioning requires Linux root")
    if not docker_uses_apparmor():
        raise RuntimeError("This Docker daemon does not use AppArmor")
    name, content = _policy(root)
    installed = PROFILE_DIRECTORY / name
    if installed.is_symlink():
        raise RuntimeError("Refusing a symlink at the worker AppArmor policy path")
    if installed.exists():
        if installed.read_bytes() != content:
            raise RuntimeError("Refusing to replace a different worker AppArmor policy")
    else:
        with installed.open("xb") as output:
            output.write(content)
        installed.chmod(0o644)
    # Validate ownership/mode before a privileged parser can read an existing file.
    verify_installed_profile(name, content.decode("utf-8"))
    if not _loaded(name):
        subprocess.run(
            ["apparmor_parser", "--add", "--skip-cache", str(installed)],
            check=True,
            timeout=30,
        )
    verify_installed_profile(name, content.decode("utf-8"))
    if not _loaded(name):
        raise RuntimeError(f"Worker AppArmor policy {name} is not loaded in the expected mode")
    return name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("policy-name", "emit-profile", "check", "install"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    if args.action == "policy-name":
        print(profile_name(args.root))
    elif args.action == "emit-profile":
        print(profile_text(args.root), end="")
    elif args.action == "check":
        print(apparmor_security_option(args.root) or "AppArmor is not used by this Docker daemon")
    else:
        print(install_policy(args.root))


if __name__ == "__main__":
    main()

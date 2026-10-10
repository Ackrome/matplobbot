"""Mandatory Linux filesystem/process/network boundary for untrusted renderers."""

import os
import shutil
import stat
import sys
from pathlib import Path


class RenderSandboxUnavailable(RuntimeError):
    """The renderer must not run when its isolation boundary is unavailable."""


# Deliberately exclude /app, /shared_lib, /home, /run, host /tmp, and host /proc.
# These are image-owned compiler/runtime/font resources, never user-controlled mounts.
RUNTIME_PATHS = (
    "/usr",
    "/bin",
    "/sbin",
    "/lib",
    "/lib64",
    "/opt/venv",
    "/etc/alternatives",
    "/etc/fonts",
    "/etc/texmf",
    "/etc/ghostscript",
    "/etc/ld.so.cache",
    "/etc/localtime",
    "/var/lib/texmf",
    "/var/cache/fontconfig",
)


def sandbox_command(command, *, workdir, resources=(), timeout=60):
    """Build a fail-closed bubblewrap command; no caller environment is inherited.

    ``workdir`` is a fresh server-created job directory, not a user supplied path.
    ``resources`` contains explicit, trusted image-owned filter/config files only.
    Absolute job paths remain valid inside the isolated root for Pandoc/SyncTeX.
    """
    if sys.platform != "linux":
        raise RenderSandboxUnavailable("Server rendering requires the Linux sandbox worker")
    if os.geteuid() == 0:
        raise RenderSandboxUnavailable("Server rendering requires a non-root worker")
    bwrap = shutil.which("bwrap")
    if not bwrap or not Path("/usr/bin/prlimit").is_file():
        raise RenderSandboxUnavailable("Renderer sandbox dependencies are unavailable")
    directory = Path(workdir).resolve(strict=True)
    if not directory.is_dir() or directory == Path(directory.anchor):
        raise ValueError("A dedicated render working directory is required")
    if not isinstance(command, (list, tuple)) or not command:
        raise ValueError("A renderer argument list is required")

    args = [
        bwrap,
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--clearenv",
    ]
    for raw in RUNTIME_PATHS:
        path = Path(raw)
        if path.exists():
            # Reproduce distro usr-merge symlinks instead of creating conflicting mounts.
            if path.is_symlink():
                args += ["--symlink", os.readlink(path), raw]
            else:
                args += ["--ro-bind", raw, raw]
    args += [
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--size",
        "134217728",
        "--tmpfs",
        "/tmp",
        "--dir",
        "/home/render",
        "--bind",
        str(directory),
        str(directory),
    ]
    for raw in resources:
        path = Path(raw).resolve(strict=True)
        if not path.is_file() or path.is_relative_to(directory):
            raise ValueError("Sandbox resources must be trusted regular files")
        args += ["--ro-bind", str(path), str(path)]
    environment = {
        "PATH": "/opt/venv/bin:/usr/local/bin:/usr/bin:/bin",
        "HOME": "/home/render",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TMPDIR": str(directory),
        "XDG_CACHE_HOME": "/tmp/cache",
        "openin_any": "p",
        "openout_any": "p",
        "shell_escape": "f",
        "TEXMFOUTPUT": str(directory),
        # The image's Chromium is used; no browser install or download is allowed.
        "PUPPETEER_EXECUTABLE_PATH": "/usr/lib/chromium/chromium",
    }
    for key, value in environment.items():
        args += ["--setenv", key, value]
    cpu = max(1, min(120, int(timeout) + 1))
    args += [
        "--chdir",
        str(directory),
        "--",
        "/usr/bin/prlimit",
        f"--cpu={cpu}:{cpu}",
        "--fsize=67108864:67108864",
        "--nproc=128:128",
        "--nofile=256:256",
        "--core=0:0",
        "--",
        *[str(value) for value in command],
    ]
    return args


def run_render_process(command, *, workdir, resources=(), studio_job_id=None, **kwargs):
    """Execute through the cancellable transport, always inside the sandbox."""
    from .studio_process import run_studio_process

    if kwargs.pop("shell", False) or "env" in kwargs or "cwd" in kwargs:
        raise ValueError("Renderer environment, shell and working directory are fixed")
    wrapped = sandbox_command(
        command, workdir=workdir, resources=resources, timeout=kwargs.get("timeout", 60)
    )
    result = run_studio_process(wrapped, studio_job_id=studio_job_id, **kwargs)
    # The host later opens PDF/log/cache files. Never let a renderer leave a link
    # which would resolve outside its isolated root when opened by the worker.
    for directory, folders, files in os.walk(workdir, followlinks=False):
        for name in folders + files:
            mode = Path(directory, name).lstat().st_mode
            if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise RenderSandboxUnavailable("Renderer produced an unsafe filesystem entry")
    # A denied namespace/mount must be an error, never a retry without isolation.
    if result.returncode != 0:
        error = result.stderr or b""
        if isinstance(error, bytes):
            error = error.decode("utf-8", "replace")
        if "bwrap:" in error:
            raise RenderSandboxUnavailable("Renderer sandbox could not be started")
    return result

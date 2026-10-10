"""Provision the checksum-pinned Node binary for Jenkins' Linux x64 quality gate."""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_NODE_BYTES = 256 * 1024 * 1024


def configuration(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        set(value) != {"version", "platform", "architecture", "archive_sha256"}
        or not re.fullmatch(r"\d+\.\d+\.\d+", value.get("version", ""))
        or not re.fullmatch(r"[0-9a-f]{64}", value.get("archive_sha256", ""))
        or (value["platform"], value["architecture"]) != ("linux", "x64")
    ):
        raise ValueError("Invalid pinned Node runtime configuration")
    return value


def sha256(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def private_directory(path):
    if path.is_symlink():
        raise ValueError("Node cache directory must not be a symlink")
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022:
        raise ValueError("Node cache must not be writable by other users")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise ValueError("Node cache must belong to the current user")


def download(url, destination):
    """Download to a private staging file; never execute or unpack this response."""
    with urllib.request.urlopen(url, timeout=60) as response, destination.open("wb") as output:
        if response.geturl() != url:
            raise ValueError("Unexpected Node archive redirect")
        size = 0
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_ARCHIVE_BYTES:
                raise ValueError("Node archive exceeds the download size limit")
            output.write(chunk)


def provision(config_path, cache):
    config = configuration(config_path)
    if platform.system() != "Linux" or platform.machine().lower() not in {"x86_64", "amd64"}:
        raise ValueError("Pinned Jenkins Node runtime requires Linux x86_64")
    name = f"node-v{config['version']}-linux-x64"
    cache = Path(cache).absolute()
    private_directory(cache)
    directory = cache / f"{name}-{config['archive_sha256'][:12]}"
    private_directory(directory)
    archive = directory / f"{name}.tar.xz"
    if archive.is_symlink():
        raise ValueError("Cached Node archive must not be a symlink")
    if not archive.exists():
        with tempfile.TemporaryDirectory(prefix="download-", dir=directory) as staging:
            partial = Path(staging) / "archive.tar.xz"
            download(f"https://nodejs.org/dist/v{config['version']}/{archive.name}", partial)
            if sha256(partial) != config["archive_sha256"]:
                raise ValueError("Downloaded Node archive checksum mismatch")
            os.replace(partial, archive)
    if not archive.is_file() or sha256(archive) != config["archive_sha256"]:
        raise ValueError("Cached Node archive checksum mismatch")
    binary_directory = directory / "bin"
    private_directory(binary_directory)
    binary = binary_directory / "node"
    if binary.is_symlink():
        raise ValueError("Cached Node binary must not be a symlink")
    # Reconstruct only this regular member on every run. The cached executable
    # is never trusted or executed before comparison with the verified archive.
    with tarfile.open(archive, "r:xz") as package:
        members = [item for item in package.getmembers() if item.name == f"{name}/bin/node"]
        if (
            len(members) != 1
            or not members[0].isfile()
            or not 0 < members[0].size <= MAX_NODE_BYTES
        ):
            raise ValueError("Node archive must contain one regular bin/node member")
        with tempfile.TemporaryDirectory(prefix="binary-", dir=directory) as staging:
            verified = Path(staging) / "node"
            with package.extractfile(members[0]) as source, verified.open("wb") as output:
                shutil.copyfileobj(source, output)
            verified.chmod(0o700)
            if not binary.is_file() or sha256(binary) != sha256(verified):
                os.replace(verified, binary)
            else:
                binary.chmod(0o700)
    # Isolate the version probe from inherited NODE_OPTIONS and loader settings.
    result = subprocess.run(
        [str(binary), "-p", "JSON.stringify([process.version,process.platform,process.arch])"],
        env={"PATH": str(binary_directory)},
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if json.loads(result.stdout) != [f"v{config['version']}", "linux", "x64"]:
        raise ValueError("Pinned Node runtime version/platform verification failed")
    return binary_directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path(__file__).with_name("node_runtime.json")
    )
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache/matplobbot/node")
    args = parser.parse_args()
    # stdout is exclusively the verified bin directory for the caller's PATH.
    print(provision(args.config, args.cache))


if __name__ == "__main__":
    main()

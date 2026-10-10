"""Consistent PostgreSQL backups and a destructive-only-to-disposable restore drill."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path


def command(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def file_sha256(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


class Snapshot:
    """Keep one exported read-only snapshot alive for pg_dump and row witnesses."""

    def __init__(self, prefix):
        self.process = subprocess.Popen(
            [
                *prefix,
                "sh",
                "-c",
                'exec psql -XqAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self.query("SET TIME ZONE 'UTC'; SET DateStyle='ISO, YMD'; SET bytea_output='hex';")

    def query(self, sql):
        marker = "end_" + uuid.uuid4().hex
        self.process.stdin.write(sql + f"\n\\echo {marker}\n")
        self.process.stdin.flush()
        output = []
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError("PostgreSQL witness query failed")
            if line.rstrip() == marker:
                return output
            output.append(line.rstrip("\n"))

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            self.process.wait(timeout=15)


def witness(snapshot):
    tables = snapshot.query(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;"
    )
    result = {}
    for table in tables:
        identifier = '"' + table.replace('"', '""') + '"'
        rows = snapshot.query(
            f"SELECT count(*) || ':' || md5(coalesce(string_agg(md5(row_to_json(t)::text), '' "
            f"ORDER BY md5(row_to_json(t)::text)), '')) FROM public.{identifier} t;"
        )
        result[table] = rows[0]
    return result


def backup(prefix, destination):
    """Create a custom-format dump; metadata hashes rows from the same DB snapshot."""
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.with_suffix(".json").exists():
        raise ValueError("Refusing to replace an existing backup")
    snapshot = Snapshot(prefix)
    try:
        snapshot.query(
            "SET statement_timeout='5min'; SET idle_in_transaction_session_timeout='5min'; BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;"
        )
        snapshot_id = snapshot.query("SELECT pg_export_snapshot();")[0]
        if not re.fullmatch(r"[0-9A-Fa-f-]+", snapshot_id):
            raise ValueError("Unexpected PostgreSQL snapshot identifier")
        rows = witness(snapshot)
        heads = snapshot.query("SELECT version_num FROM alembic_version ORDER BY version_num;")
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as output:
            command(
                [
                    *prefix,
                    "sh",
                    "-c",
                    'exec pg_dump -Fc --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB" --snapshot="$1"',
                    "dump",
                    snapshot_id,
                ],
                stdout=output,
            )
        digest = file_sha256(destination)
        metadata = {
            "format": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "sha256": digest,
            "schema_heads": heads,
            "tables": rows,
        }
        meta_path = destination.with_suffix(".json")
        with os.fdopen(
            os.open(meta_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8"
        ) as output:
            json.dump(metadata, output, indent=2)
        return metadata
    except Exception:
        # Keep incomplete evidence distinctly named; never advertise it as a backup.
        if destination.exists():
            destination.rename(destination.with_suffix(".failed"))
        raise
    finally:
        snapshot.close()


def restore_drill(dump, *, postgres_image="postgres:15-alpine"):
    """Restore into a fresh, network-isolated container. No production target option."""
    dump = Path(dump).resolve()
    metadata = json.loads(dump.with_suffix(".json").read_text(encoding="utf-8"))
    if file_sha256(dump) != metadata["sha256"]:
        raise ValueError("Backup checksum mismatch")
    name = "mpb-restore-" + uuid.uuid4().hex[:16]
    password = uuid.uuid4().hex
    started = time.monotonic()
    command(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--network",
            "none",
            "--label",
            "matplobbot.disposable=restore",
            "-e",
            "POSTGRES_USER=rc",
            "-e",
            "POSTGRES_DB=rc",
            "-e",
            f"POSTGRES_PASSWORD={password}",
            postgres_image,
        ],
        stdout=subprocess.DEVNULL,
    )
    try:
        for _ in range(60):
            result = subprocess.run(
                ["docker", "exec", name, "pg_isready", "-U", "rc", "-d", "rc"], capture_output=True
            )
            if result.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Restore PostgreSQL did not start")
        with dump.open("rb") as source:
            command(
                [
                    "docker",
                    "exec",
                    "-i",
                    name,
                    "pg_restore",
                    "--exit-on-error",
                    "--no-owner",
                    "--no-acl",
                    "-U",
                    "rc",
                    "-d",
                    "rc",
                ],
                stdin=source,
            )
        snapshot = Snapshot(["docker", "exec", "-i", name])
        try:
            actual = witness(snapshot)
            heads = snapshot.query("SELECT version_num FROM alembic_version ORDER BY version_num;")
        finally:
            snapshot.close()
        if actual != metadata["tables"] or heads != metadata["schema_heads"]:
            raise RuntimeError("Restored schema/row fingerprints differ from backup snapshot")
        return {
            "restore_verified": True,
            "restore_seconds": round(time.monotonic() - started, 2),
            "tables_verified": len(actual),
            "schema_heads": heads,
            "backup_sha256": metadata["sha256"],
        }
    finally:
        # Only this fresh generated container and its anonymous data volume are removed.
        command(["docker", "rm", "-fv", name], stdout=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    save = sub.add_parser("backup")
    save.add_argument("--compose-file", action="append", default=[])
    save.add_argument("--output", type=Path, required=True)
    restore = sub.add_parser("restore-drill")
    restore.add_argument("dump", type=Path)
    restore.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "backup":
        prefix = ["docker", "compose"]
        for path in args.compose_file or ["docker-compose.prod.yml"]:
            prefix += ["-f", path]
        backup([*prefix, "exec", "-T", "postgres"], args.output)
        print("Consistent backup and snapshot witnesses saved.")
    else:
        report = restore_drill(args.dump)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("Isolated restore verified.")


if __name__ == "__main__":
    main()

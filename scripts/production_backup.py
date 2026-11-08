#!/usr/bin/env python3
"""Consistent SQLite snapshots and non-destructive restore verification (stdlib only)."""

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def inspect_database(path: Path) -> dict:
    """Return integrity and anonymous table fingerprints, never client contents."""
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.execute("BEGIN")  # One consistent view across table counts and fingerprints.
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("integrity_check_failed")
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("foreign_key_check_failed")
        tables = {}
        names = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
        for (name,) in names:
            quoted = '"' + name.replace('"', '""') + '"'
            columns = db.execute(f"PRAGMA table_info({quoted})").fetchall()
            primary = sorted((c[5], c[0] + 1) for c in columns if c[5])
            order = ",".join(str(index) for _, index in primary) or ",".join(
                str(i + 1) for i in range(len(columns))
            )
            digest = hashlib.sha256()
            count = 0
            for row in db.execute(f"SELECT * FROM {quoted} ORDER BY {order}"):
                digest.update(json.dumps(row, ensure_ascii=False, default=str).encode())
                digest.update(b"\n")
                count += 1
            tables[name] = {"rows": count, "sha256": digest.hexdigest()}
        revision = (
            [r[0] for r in db.execute("SELECT version_num FROM alembic_version ORDER BY 1")]
            if "alembic_version" in tables
            else []
        )
    return {"integrity": "ok", "foreign_keys": "ok", "revisions": revision, "tables": tables}


def snapshot(source: Path, target: Path) -> dict:
    """Never overwrite an existing destination; SQLite Backup API includes live WAL data."""
    source = source.resolve()
    target = target.absolute()
    if not source.is_file() or source == target.resolve():
        raise ValueError("invalid_snapshot_path")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src:
            with sqlite3.connect(target) as dst:
                src.backup(dst, pages=256, sleep=0.05)
        result = inspect_database(target)
        with target.open("rb") as file:
            result["file_sha256"] = hashlib.file_digest(file, "sha256").hexdigest()
            os.fsync(file.fileno())
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return result
    except Exception:
        target.unlink(missing_ok=True)
        raise


def backup(source: Path, directory: Path, keep: int = 48) -> Path:
    if keep < 1:
        raise ValueError("invalid_retention")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    target = directory / f"cqa-{stamp}-{uuid4().hex[:8]}.sqlite3"
    result = snapshot(source, target)
    result["created_at"] = datetime.now(UTC).isoformat()
    manifest = target.with_suffix(".json")
    with os.fdopen(os.open(manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as file:
        json.dump(result, file, indent=2)
        file.flush()
        os.fsync(file.fileno())
    # Prune only our own verified snapshots after a successful new snapshot.
    snapshots = sorted(directory.glob("cqa-*.sqlite3"), reverse=True)
    for old in snapshots[keep:]:
        if old.with_suffix(".json").is_file():
            old.unlink()
            old.with_suffix(".json").unlink()
    return target


def verify_restore(source: Path, directory: Path | None = None) -> dict:
    expected = inspect_database(source)
    with tempfile.TemporaryDirectory(prefix="cqa-restore-test-", dir=directory) as temp:
        restored = snapshot(source, Path(temp) / "restored.sqlite3")
        if any(restored[key] != expected[key] for key in ("tables", "revisions")):
            raise ValueError("restore_mismatch")
    return {
        "restore": "verified",
        "tables": len(expected["tables"]),
        "rows": {k: v["rows"] for k, v in expected["tables"].items()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    make = commands.add_parser("backup")
    make.add_argument("--database", required=True, type=Path)
    make.add_argument("--directory", required=True, type=Path)
    make.add_argument("--keep", type=int, default=48)
    verify = commands.add_parser("verify-restore")
    verify.add_argument("--backup", required=True, type=Path)
    verify.add_argument("--directory", type=Path)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--database", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.action == "backup":
            print(json.dumps({"backup": str(backup(args.database, args.directory, args.keep))}))
        elif args.action == "verify-restore":
            print(json.dumps(verify_restore(args.backup, args.directory)))
        else:
            print(json.dumps(inspect_database(args.database), indent=2))
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(json.dumps({"error": "backup_failed", "category": type(exc).__name__}))
        sys.exit(1)


if __name__ == "__main__":
    main()

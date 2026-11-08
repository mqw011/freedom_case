import importlib.util
import sqlite3
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "production_backup", Path(__file__).resolve().parents[2] / "scripts/production_backup.py"
)
backup_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup_module)


def test_backup_includes_wal_and_restore_keeps_all_snapshots(tmp_path, migrated_template):
    source = tmp_path / "live.db"
    backup_module.snapshot(migrated_template, source)
    with sqlite3.connect(source) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, text TEXT NOT NULL)")
        writer.execute("INSERT INTO sample VALUES (1, 'Синтетический тест — Қазақша')")
        writer.commit()
        output = backup_module.backup(source, tmp_path / "backups")
        report = backup_module.verify_restore(output)
        assert report["restore"] == "verified"
        assert report["rows"]["sample"] == 1
        assert report["rows"]["criteria"] == 8
        assert output.stat().st_mode & 0o777 == 0o600
        assert "Синтетический" not in output.with_suffix(".json").read_text()
        assert backup_module.inspect_database(output) == backup_module.inspect_database(source)


def test_snapshot_refuses_overwrite_and_missing_source(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
    target = tmp_path / "existing.db"
    target.write_text("Must remain untouched")
    with pytest.raises(FileExistsError):
        backup_module.snapshot(source, target)
    assert target.read_text() == "Must remain untouched"
    with pytest.raises(ValueError):
        backup_module.snapshot(tmp_path / "missing.db", tmp_path / "new.db")
    assert not (tmp_path / "new.db").exists()


def test_retention_only_removes_owned_snapshots(tmp_path, migrated_template):
    directory = tmp_path / "backups"
    first = backup_module.backup(migrated_template, directory, keep=1)
    other = directory / "operator-backup.db"
    other.write_bytes(b"not ours")
    second = backup_module.backup(migrated_template, directory, keep=1)
    assert not first.exists() and second.exists() and other.exists()
    assert not first.with_suffix(".json").exists()


def test_invalid_foreign_keys_rejected(tmp_path):
    source = tmp_path / "bad.db"
    with sqlite3.connect(source) as db:
        db.executescript(
            "CREATE TABLE p(id INTEGER PRIMARY KEY); "
            "CREATE TABLE c(id INTEGER PRIMARY KEY, p_id INTEGER REFERENCES p(id)); "
            "INSERT INTO c VALUES (1, 99);"
        )
    with pytest.raises(ValueError, match="foreign_key_check"):
        backup_module.snapshot(source, tmp_path / "copy.db")
    assert not (tmp_path / "copy.db").exists()

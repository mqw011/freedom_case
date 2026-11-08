"""Operator-only SSH snapshot transport; no HTTP endpoint and no service restart."""

import hashlib
import json
import os
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from app.results.contract import ResultsError

# Existing deployment paths, not credentials. SSH authentication remains in ssh-agent.
REMOTE_SCRIPT = r"""
import hashlib,json,os,sqlite3,tempfile
from pathlib import Path
source=Path('/workspace/cqa/data/cqa.db')
if not source.is_file(): raise SystemExit(1)
fd,name=tempfile.mkstemp(prefix='results-export-',suffix='.sqlite3',dir='/workspace/cqa/backups')
os.close(fd)
try:
 with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src:
  with sqlite3.connect(name) as dst:
   src.backup(dst,pages=256,sleep=0.05)
   if dst.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]: raise ValueError()
   if dst.execute('PRAGMA foreign_key_check').fetchone(): raise ValueError()
 print(json.dumps({'name':Path(name).name,'sha256':hashlib.sha256(Path(name).read_bytes()).hexdigest()}))
except BaseException:
 Path(name).unlink(missing_ok=True)
 raise SystemExit(1)
"""


def execute(args, *, content=None):
    try:
        result = subprocess.run(args, input=content, capture_output=True, timeout=180, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ResultsError("runpod_snapshot_connection_failed") from None
    if result.returncode:
        raise ResultsError("runpod_snapshot_transfer_failed")
    return result.stdout


@contextmanager
def runpod_snapshot(root):
    root = Path(root)
    config = root / "backend/data/runpod-stage4.ssh_config"
    if not config.is_file():
        raise ResultsError("runpod_ssh_config_missing")
    ssh = ["ssh", "-o", "BatchMode=yes", "-F", str(config), "cqa-stage4"]
    raw = execute([*ssh, "python3 -"], content=REMOTE_SCRIPT.encode())
    try:
        metadata = json.loads(raw)
        name, digest = metadata["name"], metadata["sha256"]
        import re

        if not re.fullmatch(r"results-export-[a-zA-Z0-9_-]+\.sqlite3", name):
            raise ValueError()
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise ResultsError("runpod_snapshot_invalid_metadata") from None
    directory = root / "backend/data/results-source"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with tempfile.TemporaryDirectory(prefix="submission-", dir=directory) as temporary:
            target = Path(temporary) / "snapshot.sqlite3"
            execute(
                [
                    "scp",
                    "-q",
                    "-o",
                    "BatchMode=yes",
                    "-F",
                    str(config),
                    f"cqa-stage4:/workspace/cqa/backups/{name}",
                    str(target),
                ]
            )
            os.chmod(target, 0o600)
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise ResultsError("runpod_snapshot_checksum_mismatch")
            yield target
    finally:
        # Only this generated, name-validated temporary snapshot is removed.
        execute([*ssh, f"rm -- /workspace/cqa/backups/{name}"])

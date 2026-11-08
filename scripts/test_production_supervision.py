#!/usr/bin/env python3
"""Verify real Supervisor API/worker crash recovery and scheduled backup on an empty test DB.

Ollama is deliberately not started. This test does not claim GPU or inference validation.
"""

import json
import os
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
from production_backup import verify_restore
from production_config import render

REPOSITORY = Path(__file__).resolve().parents[1]
TOOLS = ["uvx", "--from", "supervisor==4.3.0"]


def wait_until(probe, seconds=55):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            result = probe()
            if result:
                return result
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(0.25)
    raise RuntimeError("supervision_check_timeout")


def main():
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 8000))
    with tempfile.TemporaryDirectory(prefix="cqa-supervision-test-") as directory:
        root = Path(directory)
        render(root, REPOSITORY, "example.invalid", "synthetic-not-loaded", worker=True)
        environment = root / "secrets/backend.env"
        with environment.open("a") as stream:
            stream.write("\nAI_LEASE_SECONDS=15\nAI_POLL_SECONDS=0.25\n")
        configuration = root / "config/supervisord.conf"
        content = configuration.read_text()
        for name in ("ollama", "proxy"):
            start = content.index(f"[program:{name}]")
            end = content.find("\n[", start + 1)
            content = content[:start] + content[end + 1 :]
        # Production uses hourly events; accelerate only this isolated acceptance test.
        configuration.write_text(content.replace("events=TICK_3600", "events=TICK_5"))
        python = str(REPOSITORY / "backend/.venv/bin/python")
        subprocess.run(
            [
                python,
                str(REPOSITORY / "scripts/production_service.py"),
                "--root",
                str(root),
                "migrate",
            ],
            check=True,
            capture_output=True,
        )
        with (root / "supervisor-test.log").open("w") as logfile:
            process = subprocess.Popen(
                [*TOOLS, "supervisord", "-n", "-c", str(configuration)],
                stdout=logfile,
                stderr=subprocess.STDOUT,
            )
        ctl = [*TOOLS, "supervisorctl", "-c", str(configuration)]

        def pid(name):
            result = subprocess.run([*ctl, "pid", name], capture_output=True, text=True)
            return int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0

        try:
            with httpx.Client(
                base_url="http://127.0.0.1:8000", trust_env=False, timeout=3
            ) as client:
                wait_until(lambda: client.get("/api/health").status_code == 200)
                wait_until(lambda: client.get("/api/ai/health").json()["worker"]["available"])
                api_pid, worker_pid = pid("api"), pid("worker")
                assert api_pid and worker_pid
                os.kill(api_pid, signal.SIGKILL)
                wait_until(lambda: pid("api") not in {0, api_pid})
                wait_until(lambda: client.get("/api/health").status_code == 200)
                assert pid("worker") == worker_pid
                os.kill(worker_pid, signal.SIGKILL)
                wait_until(lambda: pid("worker") not in {0, worker_pid})

                # Require a fresh owner heartbeat after lease expiry, not just a new process.
                def fresh_worker():
                    payload = client.get("/api/ai/health").json()
                    import sqlite3

                    with sqlite3.connect(root / "data/cqa.db") as db:
                        heartbeat = db.execute(
                            "SELECT heartbeat_at FROM ai_worker_lease"
                        ).fetchone()
                    return payload["worker"]["available"] and heartbeat

                time.sleep(16)  # Bounded wait below one minute for this test's old lease to expire.
                wait_until(fresh_worker)
                assert client.get("/api/conversations").json()["total"] == 0
                wait_until(lambda: list((root / "backups").glob("cqa-*.sqlite3")))
                snapshots = sorted((root / "backups").glob("cqa-*.sqlite3"))
                assert verify_restore(snapshots[-1])["restore"] == "verified"
                wait_until(
                    lambda: (
                        subprocess.run(
                            [*ctl, "status"], capture_output=True, text=True
                        ).stdout.count("RUNNING")
                        == 3
                    ),
                    seconds=15,
                )
                print(
                    json.dumps(
                        {
                            "supervision": "passed",
                            "api_crash_restart": "passed",
                            "worker_lease_recovery": "passed",
                            "scheduled_backup": "passed",
                            "restore": "verified",
                            "inference": "not_run",
                            "runpod_restart": "not_verified",
                        }
                    )
                )
        finally:
            subprocess.run([*ctl, "shutdown"], capture_output=True)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    main()

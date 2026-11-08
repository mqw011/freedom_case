#!/usr/bin/env python3
"""Supervisor launcher. Load secrets without shell expansion or exposing them in argv."""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values
from production_backup import backup


def load_runtime(root):
    runtime = json.loads((root / "config/runtime.json").read_text())
    env_path = root / "secrets/backend.env"
    if env_path.stat().st_mode & 0o077:
        raise ValueError("backend_env_must_be_private")
    # Signed URLs may contain $, &, quotes: never source this file through a shell.
    env = {
        key: value
        for key, value in dotenv_values(env_path, interpolate=False).items()
        if value is not None
    }
    if env.get("AI_AUTO_START_WORKER", "false").lower() != "false":
        raise ValueError("separate_worker_required")
    expected_database = "sqlite:///" + str(root / "data/cqa.db")
    if env.get("DATABASE_URL") != expected_database:
        raise ValueError("database_must_use_verified_persistent_root")
    if env.get("LLM_ALLOW_REMOTE", "false").lower() != "false":
        raise ValueError("remote_llm_not_authorized_for_this_deployment")
    if env.get("LLM_BASE_URL") != "http://127.0.0.1:11434/v1":
        raise ValueError("deployment_requires_local_ollama")
    return runtime, env


def backup_listener(root):
    # Supervisor's event protocol reserves stdout. Only safe diagnostics go to stderr.
    while True:
        sys.stdout.write("READY\n")
        sys.stdout.flush()
        header = sys.stdin.readline()
        if not header:
            return
        fields = dict(item.split(":", 1) for item in header.split())
        payload = sys.stdin.read(int(fields["len"]))
        if len(payload) != int(fields["len"]):
            raise ValueError("incomplete_supervisor_event")
        try:
            backup(root / "data/cqa.db", root / "backups", keep=48)
            print('{"event":"backup_completed"}', file=sys.stderr, flush=True)
        except Exception as exc:
            # The event is acknowledged even on failure; the failure remains in the log.
            print(
                json.dumps({"event": "backup_failed", "category": type(exc).__name__}),
                file=sys.stderr,
                flush=True,
            )
        sys.stdout.write("RESULT 2\nOK")
        sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument(
        "service", choices=("api", "worker", "ollama", "backup", "migrate", "check", "benchmark")
    )
    args = parser.parse_args()
    try:
        if os.geteuid() == 0:
            raise ValueError("run_services_as_dedicated_unprivileged_user")
        os.umask(0o077)
        root = args.root.resolve()
        runtime, values = load_runtime(root)
        release = Path(runtime["release"])
        os.chdir(release / "backend")
        env = os.environ.copy()
        env.update(values)
        env.update(
            {
                "OLLAMA_HOST": "127.0.0.1:11434",
                "OLLAMA_MODELS": str(root / "models"),
                "OLLAMA_NUM_PARALLEL": values.get("LLM_MAX_CONCURRENCY", "1"),
                "OLLAMA_MAX_LOADED_MODELS": "1",
                "OLLAMA_DEBUG": "false",
            }
        )
        if args.service == "backup":
            backup_listener(root)
            return 0
        python = str(release / "backend/.venv/bin/python")
        commands = {
            "api": [
                python,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--no-access-log",
                "--no-proxy-headers",
            ],
            "worker": [python, "-m", "app.ai.worker"],
            "ollama": [runtime["ollama"], "serve"],
            "migrate": [python, "-m", "alembic", "upgrade", "head"],
            "check": [python, "-m", "alembic", "check"],
            "benchmark": [
                python,
                "-m",
                "app.ai.benchmark",
                "--output",
                str(
                    root
                    / "data"
                    / ("benchmark-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
                ),
            ],
        }
        command = commands[args.service]
        os.execve(command[0], command, env)
    except (OSError, ValueError, KeyError):
        print('{"error":"production_service_configuration"}', file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

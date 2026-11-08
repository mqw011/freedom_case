#!/usr/bin/env python3
"""Restore private runtime state and supervised services before the existing Pod startup."""

import argparse
import json
import os
import pwd
import subprocess
import sys
from pathlib import Path

from cryptography.exceptions import InvalidTag
from production_vault import load_key, unseal


def restore_runtime(root, runtime, key, uid, gid):
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    runtime.chmod(0o700)
    if runtime.stat().st_mode & 0o077:
        raise ValueError("private_runtime_required")
    for name in ("state", "secrets", "home"):
        directory = runtime / name
        directory.mkdir(mode=0o700, exist_ok=True)
        directory.chmod(0o700)
    unseal(root / "secrets.vault", runtime / "secrets", key)
    for path in [runtime, *runtime.rglob("*")]:
        os.chown(path, uid, gid)
    for name, target in (("run", runtime / "state"), ("secrets", runtime / "secrets")):
        path = root / name
        if path.is_symlink():
            if path.resolve() != target:
                raise ValueError("unexpected_runtime_link")
        elif path.exists():
            raise ValueError("existing_runtime_path_not_overwritten")
        else:
            path.symlink_to(target, target_is_directory=True)


def service_environment(environ):
    allowed = {
        "PATH",
        "LANG",
        "LC_ALL",
        "TZ",
        "LD_LIBRARY_PATH",
        "CUDA_VISIBLE_DEVICES",
        "NVIDIA_VISIBLE_DEVICES",
        "NVIDIA_DRIVER_CAPABILITIES",
    }
    return {key: value for key, value in environ.items() if key in allowed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, default=Path("/run/cqa"))
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--start-services-only", action="store_true")
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise ValueError("bootstrap_requires_container_admin")
        root, runtime = args.root.resolve(), args.runtime_root.resolve()
        key = load_key(args.key_file)
        # Do not let the base image's environment export/Jupyter inherit the vault key.
        os.environ.pop("CQA_VAULT_KEY", None)
        try:
            account = pwd.getpwnam("cqa")
            if account.pw_uid != 2001:
                raise ValueError("unexpected_service_account")
        except KeyError:
            subprocess.run(
                [
                    "useradd",
                    "--user-group",
                    "--uid",
                    "2001",
                    "--home-dir",
                    str(runtime / "home"),
                    "--shell",
                    "/bin/bash",
                    "cqa",
                ],
                check=True,
                capture_output=True,
            )
            account = pwd.getpwnam("cqa")
        if account.pw_dir != str(runtime / "home"):
            subprocess.run(
                ["usermod", "--home", str(runtime / "home"), "cqa"], check=True, capture_output=True
            )
        restore_runtime(root, runtime, key, account.pw_uid, account.pw_gid)
        configuration = root / "config/supervisord.conf"
        control = root / "tools/bin/supervisorctl"
        base = ["runuser", "-u", "cqa", "--"]
        environment = service_environment(os.environ)
        running = subprocess.run(
            [*base, str(control), "-c", str(configuration), "pid"],
            env=environment,
            capture_output=True,
            text=True,
        )
        if not running.stdout.strip().isdigit():
            subprocess.run(
                [*base, str(root / "tools/bin/supervisord"), "-c", str(configuration)],
                env=environment,
                check=True,
                capture_output=True,
            )
        print(json.dumps({"runtime_restored": True, "supervisor_started": True}), flush=True)
        if not args.start_services_only:
            # Preserve the image's SSH, nginx and authenticated Jupyter startup.
            os.execv("/bin/bash", ["/bin/bash", "/start.sh"])
        return 0
    except (OSError, ValueError, KeyError, InvalidTag, subprocess.SubprocessError):
        print('{"error":"production_bootstrap_failed"}', file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

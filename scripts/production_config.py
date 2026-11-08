#!/usr/bin/env python3
"""Render private deployment configuration; never overwrite credentials or backend.env."""

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[1] / "deployment"


def safe_path(value):
    path = Path(value)
    if not path.is_absolute() or not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(path)):
        raise ValueError("absolute_path_without_shell_metacharacters_required")
    if ".." in path.parts:
        raise ValueError("parent_path_not_allowed")
    return path


def private_write(path, content, *, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if exclusive:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        with os.fdopen(os.open(path, flags, 0o600), "w") as output:
            output.write(content)
    else:
        temporary = path.with_name(path.name + "." + secrets.token_hex(8))
        try:
            private_write(temporary, content, exclusive=True)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def render(
    root,
    release,
    host,
    model,
    port=8080,
    nginx="/usr/sbin/nginx",
    ollama="/usr/local/bin/ollama",
    mime_types="/etc/nginx/mime.types",
    worker=False,
):
    root, release = safe_path(root), safe_path(release)
    if not re.fullmatch(r"(?=.{1,253}$)[a-z0-9]+(?:[a-z0-9.-]*[a-z0-9])?", host):
        raise ValueError("invalid_public_hostname")
    if not re.fullmatch(r"[A-Za-z0-9_./:-]{1,200}", model):
        raise ValueError("invalid_model_name")
    if not 1024 <= port <= 65535 or port in {8000, 8888, 11434}:
        raise ValueError("invalid_proxy_port")
    if root == release or release in root.parents:
        raise ValueError("persistent_root_must_not_be_inside_release")
    for child in (
        "config",
        "secrets",
        "data",
        "backups",
        "models",
        "logs",
        "run/client_body",
        "run/proxy_temp",
        "run/fastcgi_temp",
        "run/uwsgi_temp",
        "run/scgi_temp",
    ):
        (root / child).mkdir(parents=True, exist_ok=True, mode=0o700)
    python = release / "backend/.venv/bin/python"
    values = {
        "ROOT": str(root),
        "RELEASE": str(release),
        "HOST": host,
        "MODEL": model,
        "PORT": str(port),
        "PYTHON": str(python),
        "NGINX": str(safe_path(nginx)),
        "OLLAMA": str(safe_path(ollama)),
        "MIME_TYPES": str(safe_path(mime_types)),
        "WORKER_START": str(worker).lower(),
    }
    for name, target in (
        ("nginx.conf", root / "config/nginx.conf"),
        ("supervisord.conf", root / "config/supervisord.conf"),
        ("backend.env", root / "secrets/backend.env"),
    ):
        if name == "backend.env" and target.exists():
            continue
        content = (TEMPLATES / (name + ".template")).read_text()
        for key, value in values.items():
            content = content.replace("@@" + key + "@@", value)
        if "@@" in content:
            raise ValueError("unresolved_configuration_placeholder")
        private_write(target, content, exclusive=name == "backend.env")
    private_write(
        root / "config/runtime.json",
        json.dumps(
            {
                "release": str(release),
                "ollama": values["OLLAMA"],
                "public_host": host,
                "port": port,
                "worker_autostart": worker,
            },
            indent=2,
        ),
    )
    return {"configuration": str(root / "config"), "worker_autostart": worker}


def credentials(root, username="judge"):
    root = safe_path(root)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", username):
        raise ValueError("invalid_username")
    directory = root / "secrets"
    if any((directory / name).exists() for name in ("access.json", "access.htpasswd")):
        raise ValueError("credentials_already_exist")
    password = secrets.token_urlsafe(32)
    result = subprocess.run(
        ["openssl", "passwd", "-6", "-stdin"],
        input=password + "\n",
        capture_output=True,
        text=True,
        check=True,
    )
    hashed = result.stdout.strip()
    if not hashed.startswith("$6$"):
        raise ValueError("password_hash_failed")
    private_write(directory / "access.htpasswd", f"{username}:{hashed}\n", exclusive=True)
    private_write(
        directory / "access.json",
        json.dumps(
            {
                "username": username,
                "password": password,
            }
        ),
        exclusive=True,
    )
    return {"credentials_file": str(directory / "access.json"), "printed_secrets": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    conf = sub.add_parser("render")
    conf.add_argument("--root", required=True)
    conf.add_argument("--release", required=True)
    conf.add_argument("--host", required=True)
    conf.add_argument("--model", required=True)
    conf.add_argument("--port", type=int, default=8080)
    conf.add_argument("--nginx", default="/usr/sbin/nginx")
    conf.add_argument("--ollama", default="/usr/local/bin/ollama")
    conf.add_argument("--mime-types", default="/etc/nginx/mime.types")
    conf.add_argument("--enable-worker", action="store_true")
    auth = sub.add_parser("credentials")
    auth.add_argument("--root", required=True)
    auth.add_argument("--username", default="judge")
    args = parser.parse_args()
    try:
        if args.action == "credentials":
            result = credentials(args.root, args.username)
        else:
            result = render(
                args.root,
                args.release,
                args.host,
                args.model,
                args.port,
                args.nginx,
                args.ollama,
                args.mime_types,
                args.enable_worker,
            )
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError):
        print(json.dumps({"error": "deployment_configuration_failed"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Authenticated encryption for runtime secrets on volumes without POSIX permissions.

The 256-bit key belongs in RunPod's protected environment, never on the volume.
"""

import argparse
import base64
import json
import os
import sys
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"CQA-VAULT-1\x00"
FILES = ("backend.env", "access.htpasswd", "access.json")


def load_key(path=None):
    if path is not None:
        if path.stat().st_mode & 0o077:
            raise ValueError("key_file_permissions")
        encoded = path.read_text().strip()
    else:
        encoded = os.environ.get("CQA_VAULT_KEY", "").strip()
    key = base64.b64decode(encoded, validate=True)
    if len(key) != 32:
        raise ValueError("vault_key_required")
    return key


def seal(directory, target, key):
    payload = {}
    for name in FILES:
        path = directory / name
        if path.stat().st_mode & 0o077:
            raise ValueError("plaintext_permissions")
        payload[name] = path.read_text()
    nonce = os.urandom(12)
    encrypted = MAGIC + nonce + AESGCM(key).encrypt(nonce, json.dumps(payload).encode(), MAGIC)
    temporary = target.with_name(target.name + "." + os.urandom(8).hex())
    try:
        with os.fdopen(
            os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
        ) as out:
            out.write(encrypted)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def unseal(source, directory, key):
    encrypted = source.read_bytes()
    if not encrypted.startswith(MAGIC) or len(encrypted) > 1024 * 1024:
        raise ValueError("invalid_vault")
    offset = len(MAGIC)
    payload = json.loads(
        AESGCM(key).decrypt(encrypted[offset : offset + 12], encrypted[offset + 12 :], MAGIC)
    )
    if set(payload) != set(FILES) or not all(isinstance(v, str) for v in payload.values()):
        raise ValueError("invalid_vault_payload")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    if directory.stat().st_mode & 0o077:
        raise ValueError("runtime_filesystem_ignores_permissions")
    for name in FILES:
        target = directory / name
        temp = directory / (name + "." + os.urandom(8).hex())
        try:
            with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as out:
                out.write(payload[name])
            if temp.stat().st_mode & 0o077:
                raise ValueError("runtime_filesystem_ignores_permissions")
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "unseal"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--key-file", type=Path)
    args = parser.parse_args()
    try:
        key = load_key(args.key_file)
        if args.action == "seal":
            seal(args.directory, args.vault, key)
        else:
            unseal(args.vault, args.directory, key)
        print(json.dumps({"vault": args.action + "ed", "secret_values_printed": False}))
        return 0
    except (OSError, ValueError, InvalidTag):
        print('{"error":"vault_operation_failed"}', file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

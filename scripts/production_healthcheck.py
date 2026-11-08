#!/usr/bin/env python3
"""Safe service/queue/disk health. Nonzero on failed checks; no transcript or secret output."""

import argparse
import base64
import json
import os
import shutil
import ssl
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(base, path, credentials=None):
    headers = {"Accept": "application/json", "User-Agent": "cqa-production-healthcheck/1"}
    if credentials:
        raw = f"{credentials['username']}:{credentials['password']}".encode()
        headers["Authorization"] = "Basic " + base64.b64encode(raw).decode()
    try:
        with build_opener(NoRedirect()).open(
            Request(base + path, headers=headers), timeout=15
        ) as r:
            payload = json.loads(r.read(2 * 1024 * 1024))
            return (r.status, payload) if isinstance(payload, dict) else (0, {})
    except HTTPError as error:
        return error.code, {}
    except (URLError, TimeoutError, ValueError, OSError, ssl.SSLError):
        return 0, {}


def health(base, *, credentials=None, require_ai=False, disk=None):
    parsed = urlsplit(base)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("invalid_base_url")
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    ):
        raise ValueError("https_required")
    if credentials and parsed.scheme != "https":
        raise ValueError("credentials_require_https")
    result = {}
    status, backend = fetch(base, "/api/health", credentials)
    result["backend"] = status == 200 and backend.get("database") == "ok"
    status, ai = fetch(base, "/api/ai/health", credentials)
    result["provider"] = status == 200 and ai.get("provider", {}).get("available", False)
    result["worker"] = status == 200 and ai.get("worker", {}).get("available", False)
    result["model"] = ai.get("provider", {}).get("model")
    result["heartbeat_at"] = ai.get("worker", {}).get("heartbeat_at")
    counts = {}
    for state in ("queued", "running", "completed", "failed", "cancelled"):
        status, page = fetch(base, f"/api/ai/jobs?status={state}&limit=1", credentials)
        counts[state] = page.get("total") if status == 200 else None
    result["jobs"] = counts
    if disk:
        usage = shutil.disk_usage(disk)
        result["disk_free_bytes"] = usage.free
        result["disk_ok"] = usage.free >= 1024**3
    if credentials:
        # Verify all sensitive routes fail closed without auth, not just the UI.
        protected = {}
        for path in (
            "/",
            "/api/health",
            "/api/conversations",
            "/api/datasets/import",
            "/docs",
            "/openapi.json",
        ):
            status, _ = fetch(base, path)
            protected[path] = status in (401, 403)
        result["unauthenticated_blocked"] = protected
    result["ok"] = bool(
        result["backend"]
        and all(v is not None for v in counts.values())
        and (not require_ai or (result["provider"] and result["worker"]))
        and result.get("disk_ok", True)
        and all(result.get("unauthenticated_blocked", {}).values())
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--credentials-file", type=Path)
    parser.add_argument("--require-ai", action="store_true")
    parser.add_argument("--disk", type=Path)
    args = parser.parse_args()
    try:
        credentials = None
        if args.credentials_file:
            if os.stat(args.credentials_file).st_mode & 0o077:
                raise ValueError("credentials_file_permissions")
            credentials = json.loads(args.credentials_file.read_text())
        result = health(
            args.base_url.rstrip("/"),
            credentials=credentials,
            require_ai=args.require_ai,
            disk=args.disk,
        )
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1
    except (OSError, ValueError, KeyError):
        print(json.dumps({"ok": False, "error": "healthcheck_configuration"}))
        return 2


if __name__ == "__main__":
    sys.exit(main())

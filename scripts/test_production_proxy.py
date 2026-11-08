#!/usr/bin/env python3
"""Local-only nginx/TLS smoke on synthetic SQLite. Requires Docker and a production build."""

import json
import os
import socket
import ssl
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
from production_config import credentials, render

REPOSITORY = Path(__file__).resolve().parents[1]
IMAGE = "nginx@sha256:583b7f2fce1cdb8da5ad5c39ebd3c33b98b87d493190e548bdee1fa8c619c311"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_ready(probe):
    for _ in range(50):
        try:
            if probe():
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError("synthetic_service_start_timeout")


def main():
    if not (REPOSITORY / "frontend/dist/index.html").is_file():
        raise RuntimeError("build_frontend_with_same_origin_api_first")
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 8000))  # Refuse to interfere with an existing API.
    with tempfile.TemporaryDirectory(prefix="cqa-proxy-test-") as temp:
        root = Path(temp)
        http_port, tls_port = free_port(), free_port()
        while tls_port == http_port:
            tls_port = free_port()
        render(root, REPOSITORY, "localhost", "synthetic-not-loaded", port=http_port)
        credentials(root)
        auth = json.loads((root / "secrets/access.json").read_text())
        cert, key = root / "secrets/cert.pem", root / "secrets/key.pem"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-keyout",
                str(key),
                "-out",
                str(cert),
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=DNS:localhost,IP:127.0.0.1",
            ],
            check=True,
            capture_output=True,
        )
        os.chmod(key, 0o600)
        nginx = root / "config/nginx.conf"
        content = nginx.read_text().replace(
            f"listen {http_port};", f"listen 127.0.0.1:{http_port};"
        )
        content = content.replace('"https://localhost" 1', f'"https://127.0.0.1:{tls_port}" 1')
        tls_server = f"""
    server {{
        listen 127.0.0.1:{tls_port} ssl;
        ssl_certificate {cert};
        ssl_certificate_key {key};
        location / {{
            proxy_pass http://127.0.0.1:{http_port};
            proxy_set_header X-Forwarded-Proto https;
        }}
    }}
"""
        nginx.write_text(content.rstrip()[:-1] + tls_server + "}\n")
        name = "cqa-proxy-test-" + root.name.rsplit("-", 1)[-1]
        backend = None
        try:
            with (root / "synthetic-backend.log").open("w") as log:
                backend = subprocess.Popen(
                    [
                        str(REPOSITORY / "backend/.venv/bin/python"),
                        "-m",
                        "devtools.ui_server",
                        "--port",
                        "8000",
                    ],
                    cwd=REPOSITORY / "backend",
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
            with httpx.Client(trust_env=False) as direct:
                wait_ready(
                    lambda: direct.get("http://127.0.0.1:8000/api/health").status_code == 200
                )
            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    name,
                    "--network",
                    "host",
                    "--user",
                    f"{os.getuid()}:{os.getgid()}",
                    "--cap-drop=ALL",
                    "--read-only",
                    "--security-opt",
                    "no-new-privileges",
                    "--tmpfs",
                    "/tmp",
                    "-v",
                    f"{root}:{root}:rw",
                    "-v",
                    f"{REPOSITORY}/frontend/dist:{REPOSITORY}/frontend/dist:ro",
                    "--entrypoint",
                    "nginx",
                    IMAGE,
                    "-c",
                    str(nginx),
                    "-g",
                    "daemon off;",
                ],
                check=True,
                capture_output=True,
            )
            # Test-only self-signed TLS. Production diagnostics never disable verification.
            with httpx.Client(
                base_url=f"https://127.0.0.1:{tls_port}",
                verify=ssl.create_default_context(cafile=str(cert)),
                trust_env=False,
                timeout=1,
            ) as client:
                wait_ready(lambda: client.get("/api/health").status_code == 401)
                paths = (
                    "/",
                    "/api/health",
                    "/api/conversations",
                    "/api/datasets/import",
                    "/docs",
                    "/openapi.json",
                    "/redoc",
                )
                for path in paths:
                    response = client.get(path)
                    assert response.status_code == 401, path
                    assert response.headers["cache-control"] == "no-store"
                assert (
                    client.post("/api/datasets/import", json={"group_id": "TEST"}).status_code
                    == 401
                )
                client.auth = (auth["username"], auth["password"])
                assert client.get("/api/health").json()["database"] == "ok"
                assert (
                    client.post(
                        "/api/ai/evaluations",
                        json={"conversation_id": 1},
                        headers={"Origin": "https://untrusted.invalid"},
                    ).status_code
                    == 403
                )
                assert (
                    client.post(
                        "/api/ai/evaluations",
                        json={"conversation_id": 1},
                        headers={"Sec-Fetch-Site": "cross-site"},
                    ).status_code
                    == 403
                )
                assert (
                    client.post(
                        "/api/ai/evaluations",
                        json={"conversation_id": 1},
                        headers={"Origin": f"https://127.0.0.1:{tls_port}"},
                    ).status_code
                    == 202
                )
                assert client.get("/api/conversations?limit=1").json()["total"] == 65
                app = client.get("/")
                assert app.status_code == 200 and '<div id="root">' in app.text
                assert "cdn.jsdelivr.net" not in app.headers["content-security-policy"]
                docs = client.get("/docs")
                assert docs.status_code == 200 and "swagger-ui" in docs.text
                assert "cdn.jsdelivr.net" in docs.headers["content-security-policy"]
                assert client.get("/openapi.json").json()["openapi"].startswith("3.")
                # Import and version/evaluation/appeal workflow through the authenticated proxy.
                from smoke_api import run

                run(
                    f"https://127.0.0.1:{tls_port}/api",
                    auth=(auth["username"], auth["password"]),
                    verify=ssl.create_default_context(cafile=str(cert)),
                )
                browser_env = os.environ.copy()
                browser_env.update(
                    CQA_PROXY_URL=f"https://127.0.0.1:{tls_port}",
                    CQA_CREDENTIALS_FILE=str(root / "secrets/access.json"),
                )
                subprocess.run(
                    ["node", "../scripts/test_production_browser.mjs"],
                    cwd=REPOSITORY / "frontend",
                    env=browser_env,
                    check=True,
                )
            with httpx.Client(trust_env=False, follow_redirects=False) as plaintext:
                response = plaintext.get(f"http://127.0.0.1:{http_port}/api/conversations")
                assert response.status_code == 308
                assert "www-authenticate" not in response.headers
            print(
                json.dumps(
                    {
                        "proxy": "passed",
                        "tls": "local_test_certificate",
                        "unauthorized_routes_blocked": len(paths),
                        "data": "synthetic_only",
                        "runpod_verified": False,
                    }
                )
            )
        except Exception:
            # This entire fixture is synthetic; diagnostics contain only local paths/status.
            error_log = root / "logs/nginx-error.log"
            if error_log.exists():
                print(error_log.read_text()[-2000:])
            state = subprocess.run(["docker", "logs", name], capture_output=True, text=True)
            print(state.stderr[-2000:])
            raise
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
            if backend is not None:
                backend.terminate()
                try:
                    backend.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    backend.kill()
                    backend.wait()


if __name__ == "__main__":
    main()

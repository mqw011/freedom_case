import errno
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "production_health", Path(__file__).resolve().parents[2] / "scripts/production_healthcheck.py"
)
health_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health_module)


def test_disk_probe_cleans_up_and_reports_actual_writability(tmp_path):
    report = health_module.disk_health(tmp_path)
    assert report["disk_write_probe_ok"]
    assert list(tmp_path.iterdir()) == []
    assert "quota" in report["disk_free_scope"]


@pytest.mark.parametrize("code", [errno.EDQUOT, errno.ENOSPC, errno.EROFS])
def test_disk_probe_detects_quota_despite_shared_free_space(monkeypatch, tmp_path, code):
    def fail(**kwargs):
        raise OSError(code, "unwritable")

    monkeypatch.setattr(health_module.tempfile, "TemporaryFile", fail)
    report = health_module.disk_health(tmp_path)
    assert not report["disk_write_probe_ok"]
    assert not report["disk_ok"]


def test_offline_ai_separate_from_backend_and_queue(monkeypatch):
    def fetch(base, path, credentials=None):
        if path == "/api/health":
            return 200, {"database": "ok"}
        if path == "/api/ai/health":
            return 200, {"provider": {"available": False}, "worker": {"available": False}}
        return 200, {"total": 3}

    monkeypatch.setattr(health_module, "fetch", fetch)
    assert health_module.health("http://127.0.0.1:8000")["ok"]
    report = health_module.health("http://127.0.0.1:8000", require_ai=True)
    assert not report["ok"] and report["backend"]
    assert report["jobs"]["failed"] == 3


def test_protected_url_must_reject_unauthenticated_requests(monkeypatch):
    def fetch(base, path, credentials=None):
        return 200, {"database": "ok", "total": 0}

    monkeypatch.setattr(health_module, "fetch", fetch)
    report = health_module.health("https://example.invalid", credentials={"username": "x"})
    assert not report["ok"]
    assert not report["unauthenticated_blocked"]["/api/conversations"]


@pytest.mark.parametrize(
    "base",
    [
        "http://example.invalid",
        "https://u:p@example.invalid",
        "https://example.invalid?token=secret",
    ],
)
def test_insecure_endpoints_rejected(base):
    with pytest.raises(ValueError):
        health_module.health(base)


def test_credentials_not_sent_in_plaintext():
    with pytest.raises(ValueError, match="https"):
        health_module.health("http://localhost:8000", credentials={"username": "x"})


def test_health_transport_identifies_itself_to_gateway_and_rejects_wrong_json_shape():
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Gateway(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get("User-Agent") != "cqa-production-healthcheck/1":
                self.send_response(403)
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"[]" if self.path == "/wrong" else b'{"database":"ok"}')

        def log_message(self, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Gateway)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        assert health_module.fetch(base, "/health") == (200, {"database": "ok"})
        assert health_module.fetch(base, "/wrong") == (0, {})
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

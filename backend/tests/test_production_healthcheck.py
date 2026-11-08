import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "production_health", Path(__file__).resolve().parents[2] / "scripts/production_healthcheck.py"
)
health_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health_module)


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

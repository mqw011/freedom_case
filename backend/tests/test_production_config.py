import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def module(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


config = module("production_config")


@pytest.fixture
def service(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return module("production_service")


def test_render_keeps_existing_secrets_and_worker_requires_explicit_enable(tmp_path):
    root, release = tmp_path / "persistent", tmp_path / "release"
    config.render(root, release, "test.proxy.runpod.net", "qwen3:14b")
    secret = root / "secrets/backend.env"
    original = secret.read_text() + '\nDATASET_API_URL="https://example.invalid?sig=$x&x=y"\n'
    secret.write_text(original)
    config.render(root, release, "test.proxy.runpod.net", "qwen3:8b", worker=True)
    assert secret.read_text() == original
    assert secret.stat().st_mode & 0o777 == 0o600
    supervisor = (root / "config/supervisord.conf").read_text()
    worker = supervisor.split("[program:worker]")[1].split("[program:proxy]")[0]
    assert "autostart=true" in worker
    assert "autorestart=true" in worker
    assert "startretries=120" in worker
    assert "[inet_http_server]" not in supervisor
    nginx = (root / "config/nginx.conf").read_text()
    assert "auth_basic_user_file" in nginx
    assert "access_log off" in nginx
    assert 'proxy_set_header Authorization ""' in nginx
    assert "@@" not in nginx + supervisor + original


@pytest.mark.parametrize(
    "field,value",
    [
        ("host", "host; auth_basic off;"),
        ("host", "https://host"),
        ("model", "model\nSECRET=x"),
        ("port", 8000),
        ("port", 8888),
        ("port", 11434),
        ("nginx", "/bin/nginx;evil"),
        ("release", "/tmp/../escape"),
    ],
)
def test_reject_configuration_injection(tmp_path, field, value):
    arguments = dict(
        root=tmp_path / "root",
        release=tmp_path / "release",
        host="example.invalid",
        model="qwen3:14b",
    )
    arguments[field] = value
    with pytest.raises(ValueError):
        config.render(**arguments)


def test_credentials_private_unique_and_never_overwritten(tmp_path, capsys):
    result = config.credentials(tmp_path)
    assert result["printed_secrets"] is False
    access = tmp_path / "secrets/access.json"
    credentials = json.loads(access.read_text())
    assert len(credentials["password"]) >= 40
    assert credentials["password"] not in capsys.readouterr().out
    assert credentials["password"] not in (tmp_path / "secrets/access.htpasswd").read_text()
    assert access.stat().st_mode & 0o777 == 0o600
    before = access.read_bytes()
    with pytest.raises(ValueError, match="already_exist"):
        config.credentials(tmp_path)
    assert access.read_bytes() == before


def test_env_loaded_literally_and_separate_worker_enforced(tmp_path, service):
    config.render(tmp_path, tmp_path / "release", "example.invalid", "qwen3:14b")
    env = tmp_path / "secrets/backend.env"
    with env.open("a") as file:
        file.write('\nDATASET_API_URL="https://example.invalid?sig=${SECRET}&x=y"\n')
    runtime, values = service.load_runtime(tmp_path)
    assert values["DATASET_API_URL"] == "https://example.invalid?sig=${SECRET}&x=y"
    assert runtime["worker_autostart"] is False
    env.write_text(
        env.read_text().replace("AI_AUTO_START_WORKER=false", "AI_AUTO_START_WORKER=true")
    )
    with pytest.raises(ValueError, match="separate_worker"):
        service.load_runtime(tmp_path)


@pytest.mark.parametrize(
    "override",
    [
        "LLM_ALLOW_REMOTE=true",
        "DATABASE_URL=sqlite:////tmp/ephemeral.db",
        "LLM_BASE_URL=https://external.invalid/v1",
    ],
)
def test_service_refuses_unapproved_remote_or_ephemeral_configuration(tmp_path, service, override):
    config.render(tmp_path, tmp_path / "release", "example.invalid", "qwen3:14b")
    with (tmp_path / "secrets/backend.env").open("a") as file:
        file.write("\n" + override + "\n")
    with pytest.raises(ValueError):
        service.load_runtime(tmp_path)


def test_backup_listener_acknowledges_success_and_failure_without_secrets(
    tmp_path, service, monkeypatch
):
    calls = []

    def run_backup(source, destination, keep):
        calls.append(keep)
        if len(calls) == 2:
            raise OSError("private contents must never be logged")

    monkeypatch.setattr(service, "backup", run_backup)
    monkeypatch.setattr(
        sys, "stdin", io.StringIO("eventname:TICK_3600 len:2\nxyeventname:TICK_3600 len:2\nxy")
    )
    stdout, stderr = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    service.backup_listener(tmp_path)
    assert calls == [48, 48]
    assert stdout.getvalue().count("RESULT 2\nOK") == 2
    assert "backup_completed" in stderr.getvalue()
    assert "backup_failed" in stderr.getvalue()
    assert "private contents" not in stderr.getvalue()


@pytest.mark.parametrize("name", ["api", "worker", "check", "benchmark"])
def test_service_launch_uses_private_config_and_loopback(tmp_path, service, monkeypatch, name):
    config.render(tmp_path, tmp_path / "release", "example.invalid", "qwen3:14b")
    monkeypatch.setattr(sys, "argv", ["service", "--root", str(tmp_path), name])
    monkeypatch.setattr(service.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(service.os, "umask", lambda mask: None)
    monkeypatch.setattr(service.os, "chdir", lambda directory: None)
    captured = {}
    monkeypatch.setattr(
        service.os,
        "execve",
        lambda path, command, env: captured.update(path=path, command=command, env=env),
    )
    service.main()
    assert captured["env"]["DATABASE_URL"] == "sqlite:///" + str(tmp_path / "data/cqa.db")
    assert captured["env"]["OLLAMA_HOST"] == "127.0.0.1:11434"
    assert captured["env"]["OLLAMA_MAX_LOADED_MODELS"] == "1"
    assert captured["env"]["AI_AUTO_START_WORKER"] == "false"
    assert "DATASET_API_URL" not in " ".join(captured["command"])
    if name == "api":
        assert "127.0.0.1" in captured["command"]
        assert "--no-access-log" in captured["command"]
    if name == "benchmark":
        assert captured["command"][-1].startswith(str(tmp_path / "data/benchmark-"))


def test_service_rejects_root_before_loading_secrets(service, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["service", "--root", "/not-accessed", "api"])
    monkeypatch.setattr(service.os, "geteuid", lambda: 0)
    assert service.main() == 1
    assert "production_service_configuration" in capsys.readouterr().err

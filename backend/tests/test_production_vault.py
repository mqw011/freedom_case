import importlib.util
import os
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

spec = importlib.util.spec_from_file_location(
    "production_vault", Path(__file__).resolve().parents[2] / "scripts/production_vault.py"
)
vault = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vault)


def prepare(tmp_path):
    source = tmp_path / "source"
    source.mkdir(mode=0o700)
    for name in vault.FILES:
        path = source / name
        path.write_text("synthetic-private-value:" + name)
        path.chmod(0o600)
    return source


def test_encrypted_vault_roundtrip_and_permissions(tmp_path):
    source = prepare(tmp_path)
    key = os.urandom(32)
    encrypted = tmp_path / "secrets.vault"
    vault.seal(source, encrypted, key)
    assert b"synthetic-private-value" not in encrypted.read_bytes()
    restored = tmp_path / "restored"
    vault.unseal(encrypted, restored, key)
    for name in vault.FILES:
        assert (restored / name).read_bytes() == (source / name).read_bytes()
        assert (restored / name).stat().st_mode & 0o777 == 0o600
    assert restored.stat().st_mode & 0o777 == 0o700


def test_tampered_vault_or_wrong_key_never_changes_existing_plaintext(tmp_path):
    source = prepare(tmp_path)
    encrypted = tmp_path / "secrets.vault"
    key = os.urandom(32)
    vault.seal(source, encrypted, key)
    before = (source / "backend.env").read_bytes()
    with pytest.raises(InvalidTag):
        vault.unseal(encrypted, source, os.urandom(32))
    content = bytearray(encrypted.read_bytes())
    content[-1] ^= 1
    encrypted.write_bytes(content)
    with pytest.raises(InvalidTag):
        vault.unseal(encrypted, source, key)
    assert (source / "backend.env").read_bytes() == before


def test_vault_refuses_unprotected_plaintext_and_missing_key(tmp_path, monkeypatch):
    source = prepare(tmp_path)
    (source / "backend.env").chmod(0o644)
    with pytest.raises(ValueError, match="permissions"):
        vault.seal(source, tmp_path / "vault", os.urandom(32))
    monkeypatch.delenv("CQA_VAULT_KEY", raising=False)
    with pytest.raises(ValueError):
        vault.load_key()


def test_runtime_restores_private_files_and_links_without_exposing_vault_key(tmp_path, monkeypatch):

    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    bootstrap_spec = importlib.util.spec_from_file_location(
        "bootstrap", scripts / "production_bootstrap.py"
    )
    bootstrap = importlib.util.module_from_spec(bootstrap_spec)
    bootstrap_spec.loader.exec_module(bootstrap)
    root = tmp_path / "volume"
    root.mkdir()
    source = prepare(tmp_path)
    key = os.urandom(32)
    vault.seal(source, root / "secrets.vault", key)
    runtime = tmp_path / "runtime"
    bootstrap.restore_runtime(root, runtime, key, os.getuid(), os.getgid())
    assert (root / "secrets").is_symlink()
    assert (root / "run").resolve() == runtime / "state"
    assert (root / "secrets/backend.env").stat().st_mode & 0o777 == 0o600
    assert bootstrap.service_environment(
        {
            "CQA_VAULT_KEY": "secret",
            "JUPYTER_PASSWORD": "private",
            "PATH": "/bin",
            "CUDA_VISIBLE_DEVICES": "0",
        }
    ) == {"PATH": "/bin", "CUDA_VISIBLE_DEVICES": "0"}
    # Repeating bootstrap is safe and does not overwrite an unrelated directory.
    bootstrap.restore_runtime(root, runtime, key, os.getuid(), os.getgid())
    (root / "run").unlink()
    (root / "run").mkdir()
    (root / "run/keep").write_text("user-owned")
    with pytest.raises(ValueError, match="not_overwritten"):
        bootstrap.restore_runtime(root, runtime, key, os.getuid(), os.getgid())
    assert (root / "run/keep").read_text() == "user-owned"

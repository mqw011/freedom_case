"""Publish exactly two validated result files; non-fast-forward pushes fail safely."""

import hashlib
import subprocess
from pathlib import Path

from app.results.contract import ResultsError, read_document, write_document
from app.results.exporter import validate_against_bundle

PATHS = {"dev": "results/dev/results.json", "prod": "results/prod/results.json"}


def git(root, *args, allowed=(0,)):
    try:
        process = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, timeout=180, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ResultsError("git_command_unavailable_" + args[0]) from None
    if process.returncode not in allowed:
        # Git errors may contain a credential embedded in a remote URL.
        raise ResultsError("git_command_failed_" + args[0])
    return process


def preflight(root):
    if git(root, "branch", "--show-current").stdout.decode().strip() != "main":
        raise ResultsError("submission_requires_main")
    if git(root, "diff", "--cached", "--name-only", "-z").stdout:
        raise ResultsError("submission_requires_empty_index")
    status = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    for entry in status.split(b"\0"):
        if entry and entry[3:].decode() not in PATHS.values():
            raise ResultsError("unrelated_worktree_changes")
    git(root, "fetch", "--quiet", "origin", "main")
    if git(root, "merge-base", "--is-ancestor", "origin/main", "HEAD", allowed=(0, 1)).returncode:
        raise ResultsError("remote_main_changed_sync_required")
    ahead = git(root, "diff", "--name-only", "-z", "origin/main..HEAD").stdout
    if any(p.decode() not in PATHS.values() for p in ahead.split(b"\0") if p):
        raise ResultsError("unpublished_code_commits")


def submit(root, bundles, *, require_complete=False):
    root = Path(root).resolve()
    if set(bundles) != set(PATHS):
        raise ResultsError("both_real_datasets_required")
    reports = {
        kind: validate_against_bundle(
            bundle.document, bundle, kind, require_complete=require_complete
        )
        for kind, bundle in bundles.items()
    }
    preflight(root)
    for kind, bundle in bundles.items():
        write_document(root / PATHS[kind], bundle.document)
        validate_against_bundle(
            read_document(root / PATHS[kind]), bundle, kind, require_complete=require_complete
        )
    git(root, "add", "--", *PATHS.values())
    changed = git(root, "diff", "--cached", "--name-only", "-z").stdout
    if any(p.decode() not in PATHS.values() for p in changed.split(b"\0") if p):
        raise ResultsError("unexpected_staged_files")
    hashes = {}
    for kind, relative in PATHS.items():
        expected = (root / relative).read_bytes()
        if git(root, "show", ":" + relative).stdout != expected:
            raise ResultsError("index_contents_changed")
        hashes[kind] = hashlib.sha256(expected).hexdigest()
    git(root, "diff", "--cached", "--check")
    if changed:
        git(root, "commit", "-m", "chore(results): submit CQA schema 1.0 evaluation results")
    sha = git(root, "rev-parse", "HEAD").stdout.decode().strip()
    # Recheck committed blobs: hooks must not replace the validated files.
    for kind, relative in PATHS.items():
        if (
            hashlib.sha256(git(root, "show", sha + ":" + relative).stdout).hexdigest()
            != hashes[kind]
        ):
            raise ResultsError("committed_contents_changed")
    git(root, "push", "origin", "HEAD:refs/heads/main")
    remote = git(root, "ls-remote", "--exit-code", "origin", "refs/heads/main").stdout.decode()
    if not remote.split() or remote.split()[0] != sha:
        raise ResultsError("remote_sha_mismatch")
    return {
        "submitted": True,
        "commit_sha": sha,
        "remote_sha": sha,
        "files_sha256": hashes,
        "reports": reports,
    }

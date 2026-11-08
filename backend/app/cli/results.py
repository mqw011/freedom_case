"""Official result commands. Logs contain summaries and error codes, never rationales."""

import argparse
import json
import os
import sys
import tomllib
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.results.contract import ResultsError, read_document, validate, write_document
from app.results.exporter import ResultsExporter, snapshot_session, validate_against_bundle
from app.results.runpod import runpod_snapshot
from app.results.submission import PATHS, git, submit


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("export-dev", "export-prod", "validate-results", "submit-results"):
        command = commands.add_parser(name)
        command.add_argument("--repository", type=Path, default=Path.cwd())
        source = command.add_mutually_exclusive_group()
        source.add_argument("--database", type=Path, help="SQLite source; opened read-only")
        source.add_argument(
            "--runpod", action="store_true", help="Fresh SSH snapshot from configured CQA Pod"
        )
        command.add_argument("--team-name")
        command.add_argument("--model-mode", choices=("local", "external_api", "hybrid"))
        command.add_argument("--checklist-version", type=int)
        command.add_argument("--require-complete", action="store_true")
        if name in ("export-prod", "submit-results"):
            command.add_argument(
                "--prod-group-id",
                required=True,
                help="Actual organizer group_id already imported into SQLite",
            )
        if name == "submit-results":
            command.add_argument("--require-prod-complete", action="store_true")
        if name.startswith("export-"):
            command.add_argument("--output", type=Path)
            command.add_argument(
                "--manifest",
                type=Path,
                help="Optional private provenance; keep outside tracked results",
            )
        if name == "validate-results":
            command.add_argument("file", type=Path)
            command.add_argument("--kind", choices=("dev", "prod"), required=True)
            command.add_argument("--prod-group-id")
            command.add_argument(
                "--structural-only",
                action="store_true",
                help="No DB proof of IDs, turns, provenance or freshness",
            )
    return result


def run(args):
    if args.command == "validate-results" and args.structural_only:
        report = validate(
            read_document(args.file), kind=args.kind, require_complete=args.require_complete
        )
        return {**report, "database_verified": False}
    root = Path(git(args.repository, "rev-parse", "--show-toplevel").stdout.decode().strip())
    config_path = root / "submission.toml"
    config = (
        tomllib.loads(config_path.read_text()).get("submission", {}) if config_path.exists() else {}
    )
    team = args.team_name or config.get("team_name")
    mode = args.model_mode or config.get("model_mode")
    if not team or not mode:
        raise ResultsError("team_name_and_model_mode_required")
    settings = Settings()
    if args.database is None:
        url = make_url(settings.database_url)
        if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
            raise ResultsError("sqlite_snapshot_path_required")
        database = Path(url.database)
    else:
        database = args.database
    with snapshot_session(database) as (session, digest):
        exporter = ResultsExporter(
            session, team_name=team, model_mode=mode, fallback_model=settings.llm_model
        )
        if args.command == "submit-results":
            # Build both before writing either: a missing control set never creates a fake PROD.
            bundles = {
                "dev": exporter.build("dev", "DEV", version_id=args.checklist_version),
                "prod": exporter.build(
                    "prod", args.prod_group_id, version_id=args.checklist_version
                ),
            }
        else:
            kind = args.kind if args.command == "validate-results" else args.command[7:]
            group = "DEV" if kind == "dev" else args.prod_group_id
            bundle = exporter.build(kind, group, version_id=args.checklist_version)
    if args.command == "submit-results":
        if args.require_prod_complete:
            validate(bundles["prod"].document, kind="prod", require_complete=True)
        return submit(root, bundles, require_complete=args.require_complete)
    if args.command == "validate-results":
        return {
            **validate_against_bundle(
                read_document(args.file), bundle, kind, require_complete=args.require_complete
            ),
            "database_verified": True,
        }
    report = validate(
        bundle.document,
        kind=kind,
        expected_turns=bundle.expected_turns,
        require_complete=args.require_complete,
    )
    output = args.output or root / PATHS[kind]
    if output.resolve() == database.resolve() or output.is_symlink():
        raise ResultsError("unsafe_output_path")
    if args.manifest:
        manifest = args.manifest.resolve()
        if (
            manifest == output.resolve()
            or manifest == database.resolve()
            or root / "results" in manifest.parents
        ):
            raise ResultsError("manifest_must_be_private")
        ignored = git(root, "check-ignore", "--quiet", str(manifest), allowed=(0, 1, 128))
        if ignored.returncode != 0:
            raise ResultsError("manifest_must_be_gitignored")
        manifest.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(manifest, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as file:
            json.dump({"snapshot_sha256": digest, "provenance": bundle.provenance}, file, indent=2)
    write_document(output, bundle.document)
    return {**report, "database_verified": True, "file": str(output), "snapshot_sha256": digest}


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.runpod:
            root = Path(
                git(args.repository, "rev-parse", "--show-toplevel").stdout.decode().strip()
            )
            with runpod_snapshot(root) as database:
                args.database = database
                report = run(args)
        else:
            report = run(args)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except ResultsError as exc:
        print(json.dumps({"ok": False, "error": exc.code, "location": exc.location}))
        return 1
    except (OSError, ValueError, SQLAlchemyError):
        print(json.dumps({"ok": False, "error": "export_configuration_or_storage_error"}))
        return 1


def export_dev():
    return main(["export-dev", *sys.argv[1:]])


def export_prod():
    return main(["export-prod", *sys.argv[1:]])


def validate_results():
    return main(["validate-results", *sys.argv[1:]])


def submit_results():
    return main(["submit-results", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())

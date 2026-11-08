"""Official export regression tests; all conversations here are synthetic."""

import copy
import hashlib
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.cli.results import main
from app.models import ChecklistVersion, Conversation, Evaluation
from app.models.ai import AIJob
from app.results.contract import (
    IDS,
    ResultsError,
    dumps,
    loads,
    read_document,
    validate,
    write_document,
)
from app.results.exporter import (
    ExportBundle,
    ResultsExporter,
    snapshot_session,
    validate_against_bundle,
)
from app.results.privacy import public_rationale
from app.results.submission import PATHS, submit
from app.schemas.appeals import AppealCreate, DecisionCreate
from app.schemas.evaluations import EvaluationSubmission
from app.services.appeal_service import AppealService
from app.services.evaluation_service import EvaluationService
from tests.conftest import upload


def example():
    values = [True, None, None, 15, True, 7, True, False]
    return {
        "schema_version": "1.0",
        "team_name": "hustlers",
        "model": {"mode": "local", "name": "synthetic-test-provider"},
        "results": [
            {
                "conversation_id": "synthetic-example",
                "status": "ok",
                "criteria": [
                    dict(
                        criterion_id=name,
                        value=value,
                        rationale="Synthetic manual annotation for this test.",
                        evidence_turns=[4],
                    )
                    for name, value in zip(IDS.values(), values, strict=True)
                ],
                "score": {"final_score": Decimal("85.38"), "critical_flag": False},
            }
        ],
    }


def test_pdf_example_decimal_roundtrip():
    doc = example()
    assert validate(doc)["ok"] == 1
    assert loads(dumps(doc)) == doc
    assert '"final_score":85.38' in dumps(doc)
    assert doc["results"][0]["criteria"][5]["value"] == 7


@pytest.mark.parametrize(
    "field,value",
    [
        ("contact", None),
        ("contact", 1),
        ("empathy", "yes"),
        ("critical", None),
        ("consultation", 12),
        ("consultation", "15"),
        ("consultation", True),
        ("dialogue", 8),
        ("dialogue", None),
        ("dialogue", Decimal("10.5")),
    ],
)
def test_invalid_values(field, value):
    doc = example()
    next(c for c in doc["results"][0]["criteria"] if c["criterion_id"] == field)["value"] = value
    with pytest.raises(ResultsError):
        validate(doc)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "unknown",
        "score",
        "flag",
        "extra",
        "turn_zero",
        "turn_repeat",
        "empty_reason",
    ],
)
def test_contract_rejects_invalid_results(mutation):
    doc = example()
    row = doc["results"][0]
    if mutation == "missing":
        row["criteria"].pop()
    if mutation == "duplicate":
        row["criteria"][0] = row["criteria"][1].copy()
    if mutation == "unknown":
        row["criteria"][0]["criterion_id"] = "01"
    if mutation == "score":
        row["score"]["final_score"] = Decimal("85.39")
    if mutation == "flag":
        row["score"]["critical_flag"] = True
    if mutation == "extra":
        row["transcript"] = []
    if mutation == "turn_zero":
        row["criteria"][0]["evidence_turns"] = [0]
    if mutation == "turn_repeat":
        row["criteria"][0]["evidence_turns"] = [1, 1]
    if mutation == "empty_reason":
        row["criteria"][0]["rationale"] = "  "
    with pytest.raises(ResultsError):
        validate(doc)


def test_critical_does_not_zero_score_and_na_redistributes():
    doc = example()
    row = doc["results"][0]
    row["criteria"][7]["value"] = True
    row["score"]["critical_flag"] = True
    assert validate(doc)["ok"] == 1
    row["criteria"][1]["value"] = True
    row["criteria"][6]["value"] = False
    row["score"]["final_score"] = Decimal("81.88")
    assert validate(doc)["ok"] == 1


@pytest.mark.parametrize("text", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', "{broken"])
def test_invalid_json(text):
    with pytest.raises(ResultsError):
        loads(text)


def test_turn_bounds_duplicates_and_dataset_size():
    doc = example()
    with pytest.raises(ResultsError, match="evidence_turn_out_of_bounds"):
        validate(doc, expected_turns={"synthetic-example": 3})
    with pytest.raises(ResultsError, match="dataset_ids_mismatch"):
        validate(doc, expected_turns={"other": 100})
    with pytest.raises(ResultsError, match="dataset_count_mismatch"):
        validate(doc, kind="prod")
    doc["results"].append(copy.deepcopy(doc["results"][0]))
    with pytest.raises(ResultsError, match="duplicate_conversation_id"):
        validate(doc)


@pytest.fixture
def export_data(client, app, dataset_payload):
    record = dataset_payload["data"]["records"][0]
    records = []
    for index in range(65):
        item = copy.deepcopy(record)
        item["conversation_id"] = f"synthetic-export-{index:03}"
        if index >= 60:
            item["channel"] = "voice call"
            for j, message in enumerate(item["transcript"]):
                message["timestamp"] = f"2026-01-01T12:00:0{j}+05:00"
        records.append(item)
    dataset_payload["data"].update(dataset_group_id="DEV", total_records=65, records=records)
    assert upload(client, dataset_payload).status_code == 201
    with app.state.session_factory() as session:
        conversation = session.scalar(select(Conversation).order_by(Conversation.id).offset(1))
        messages = conversation.messages
        assert messages[-1].id != 4
        answers = ["yes", "yes", "na", "15", "yes", "7", "no", "no"]
        evaluation = EvaluationService(session).create(
            EvaluationSubmission(
                conversation_id=conversation.id,
                checklist_version_id=1,
                source="ai",
                results=[
                    dict(
                        criterion_code=code,
                        answer=answer,
                        explanation="Synthetic annotated reasoning.",
                        evidence=[
                            dict(
                                evidence_type="quote",
                                message_id=messages[-1].id,
                                excerpt=messages[-1].text,
                                explanation="Synthetic proof.",
                            )
                            if code == "01"
                            else dict(
                                evidence_type="absence" if code == "08" else "range",
                                message_id=messages[0].id,
                                end_message_id=messages[-1].id,
                                explanation="Synthetic checked interval.",
                            )
                        ],
                    )
                    for code, answer in zip(IDS, answers, strict=True)
                ],
            )
        )
        job = AIJob(
            conversation_id=conversation.id,
            checklist_version_id=1,
            model="synthetic-model",
            provider="ollama",
            inference_config={},
            request_hash="test",
            status="completed",
            evaluation_id=evaluation.id,
        )
        session.add(job)
        session.commit()
        return app, job.id, evaluation.id, conversation.id


def exporter(session):
    return ResultsExporter(
        session, team_name="hustlers", model_mode="local", fallback_model="unused"
    )


def test_export_all_65_original_ids_evidence_and_read_only(export_data):
    app, _, _, _ = export_data
    path = Path(app.state.engine.url.database)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with snapshot_session(path) as (session, _):
        bundle = exporter(session).build("dev", "DEV")
        assert validate(bundle.document, kind="dev") == dict(
            records=65, ok=1, error=64, schema_version="1.0"
        )
        row = next(r for r in bundle.document["results"] if r["status"] == "ok")
        assert row["conversation_id"] == "synthetic-export-001"
        assert row["criteria"][0]["evidence_turns"] == [4]
        assert row["criteria"][7]["evidence_turns"] == [1, 2, 3, 4]
        assert row["score"]["final_score"] == Decimal("81.88")
        assert bundle.document["model"]["name"] == "synthetic-model"
        assert "transcript" not in dumps(bundle.document)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_pending_latest_job_does_not_silently_use_old_score(export_data, tmp_path):
    app, _, evaluation_id, conversation_id = export_data
    with app.state.session_factory() as session:
        initial = exporter(session).build("dev", "DEV")
        # Technical re-evaluation has no result yet; no stale success.
        old = session.scalar(select(AIJob))
        old.evaluation_id = None
        job = AIJob(
            conversation_id=conversation_id,
            checklist_version_id=1,
            model="new-model",
            provider="ollama",
            inference_config={},
            request_hash="again",
            status="queued",
        )
        session.add(job)
        session.commit()
        pending = exporter(session).build("dev", "DEV")
        assert validate(pending.document)["error"] == 65
        with pytest.raises(ResultsError):
            validate_against_bundle(initial.document, pending, "dev")
        with pytest.raises(ResultsError, match="incomplete_evaluations"):
            validate(pending.document, require_complete=True)
        output = tmp_path / "results.json"
        write_document(output, pending.document)
        job.status = "completed"
        job.evaluation_id = evaluation_id
        session.commit()
        ready = exporter(session).build("dev", "DEV")
        write_document(output, ready.document)
        assert validate(read_document(output))["ok"] == 1
        contents = output.read_bytes()
        write_document(output, ready.document)
        assert output.read_bytes() == contents


def test_appeal_exports_current_answer_without_changing_original(export_data):
    app, _, evaluation_id, _ = export_data
    with app.state.session_factory() as session:
        evaluation = session.get(Evaluation, evaluation_id)
        result = next(r for r in evaluation.results if r.answer == "7")
        appeals = AppealService(session)
        appeal = appeals.create(
            evaluation_id, AppealCreate(criterion_result_id=result.id, comment="Test")
        )
        appeals.decide(
            appeal.id,
            DecisionCreate(
                decision="revised", revised_answer="10", reason="Reviewed synthetic answer."
            ),
        )
        session.commit()
        row = next(
            r
            for r in exporter(session).build("dev", "DEV").document["results"]
            if r["status"] == "ok"
        )
        assert row["criteria"][5]["value"] == 10
        assert row["criteria"][5]["rationale"] == "Reviewed synthetic answer."
        assert row["score"]["final_score"] == Decimal("87.50")
        assert evaluation.initial_score == Decimal("81.88")
        assert result.answer == "7"


@pytest.mark.parametrize(
    "damage", ["foreign", "missing", "reversed", "wrong_excerpt", "score", "manual"]
)
def test_damaged_evaluation_keeps_id_as_error(export_data, damage):
    app, _, evaluation_id, conversation_id = export_data
    with app.state.session_factory() as session:
        ev = session.get(Evaluation, evaluation_id)
        evidence = ev.results[0].evidence[0]
        if damage == "foreign":
            other = session.scalar(select(Conversation).where(Conversation.id != conversation_id))
            evidence.message_id = other.messages[0].id
        if damage == "missing":
            evidence.message_id = 999999
        if damage == "wrong_excerpt":
            evidence.excerpt = "not in transcript"
        if damage == "reversed":
            evidence = ev.results[1].evidence[0]
            evidence.message_id, evidence.end_message_id = (
                evidence.end_message_id,
                evidence.message_id,
            )
        if damage == "score":
            ev.final_score = Decimal("1.00")
        if damage == "manual":
            ev.source = "manual"
        # Avoid flushing an intentionally corrupted FK; check exporter defensively in memory.
        with session.no_autoflush:
            assert validate(exporter(session).build("dev", "DEV").document)["error"] == 65


def test_incompatible_checklist_and_missing_control_fail_closed(export_data):
    app, *_ = export_data
    with app.state.session_factory() as session:
        for group in (None, "DEV", "UNISSUED-CONTROL"):
            with pytest.raises(ResultsError):
                exporter(session).build("prod", group)
        version = session.get(ChecklistVersion, 1)
        version.criteria[0].weight = Decimal("11")
        with session.no_autoflush, pytest.raises(ResultsError, match="checklist_incompatible"):
            exporter(session).build("dev", "DEV")


def test_cli_export_validate_missing_prod_and_no_database_creation(export_data, tmp_path, capsys):
    app, *_ = export_data
    database = str(app.state.engine.url.database)
    output = tmp_path / "results.json"
    common = ["--database", database]
    assert main(["export-dev", *common, "--output", str(output)]) == 0
    assert main(["validate-results", str(output), "--kind", "dev", *common]) == 0
    assert (
        main(
            [
                "export-prod",
                "--prod-group-id",
                "UNISSUED",
                *common,
                "--output",
                str(tmp_path / "prod.json"),
            ]
        )
        == 1
    )
    assert not (tmp_path / "prod.json").exists()
    missing = tmp_path / "missing.db"
    assert main(["export-dev", "--database", str(missing)]) == 1
    assert not missing.exists()
    assert "Synthetic annotated" not in capsys.readouterr().out


def test_public_rationale_omits_source_and_secrets():
    source = "Synthetic client secret conversation phrase for privacy testing."
    result = public_rationale(
        f"{source} Clear reasoning. https://example.invalid?sig=secret "
        "someone@example.invalid +77001234567 token=private",
        [source],
    )
    for private in (source, "https://", "someone@", "77001234567", "private"):
        assert private not in result
    assert "Clear reasoning." in result


def test_schema_is_valid_2020_12():
    from importlib.resources import files

    from jsonschema import Draft202012Validator

    Draft202012Validator.check_schema(
        loads(files("app.results").joinpath("schema-1.0.json").read_text())
    )


def error_bundle(kind):
    count = 65 if kind == "dev" else 10
    rows = [
        dict(
            conversation_id=f"synthetic-{kind}-{i}",
            status="error",
            criteria=[],
            score=None,
            error="Test fixture, no inference.",
        )
        for i in range(count)
    ]
    doc = dict(
        schema_version="1.0",
        team_name="test",
        model={"mode": "local", "name": "test-model"},
        results=rows,
    )
    return ExportBundle(doc, {r["conversation_id"]: 4 for r in rows}, [])


def command(root, *args):
    return (
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
        .stdout.decode()
        .strip()
    )


@pytest.fixture
def publishing_repo(tmp_path):
    remote = tmp_path / "remote.git"
    root = tmp_path / "work"
    root.mkdir()
    command(tmp_path, "init", "--bare", str(remote))
    command(root, "init", "-b", "main")
    command(root, "config", "user.email", "tests@example.invalid")
    command(root, "config", "user.name", "Synthetic Test")
    (root / "README").write_text("Synthetic isolated Git integration test")
    command(root, "add", "README")
    command(root, "commit", "-m", "initial")
    command(root, "remote", "add", "origin", str(remote))
    command(root, "push", "-u", "origin", "main")
    return root, remote


def test_submit_pushes_both_exact_files_and_checks_sha_idempotently(publishing_repo):
    root, remote = publishing_repo
    bundles = {kind: error_bundle(kind) for kind in PATHS}
    report = submit(root, bundles)
    assert report["submitted"]
    assert report["commit_sha"] == command(remote, "rev-parse", "main") == report["remote_sha"]
    assert set(
        command(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()
    ) == set(PATHS.values())
    assert submit(root, bundles)["commit_sha"] == report["commit_sha"]
    assert command(root, "status", "--porcelain") == ""


@pytest.mark.parametrize("dirty", ["untracked", "staged", "code_commit"])
def test_submit_preserves_unrelated_user_work(publishing_repo, dirty):
    root, _ = publishing_repo
    path = root / "user.txt"
    path.write_text("keep this")
    if dirty in ("staged", "code_commit"):
        command(root, "add", "user.txt")
    if dirty == "code_commit":
        command(root, "commit", "-m", "unpublished code")
    with pytest.raises(ResultsError):
        submit(root, {k: error_bundle(k) for k in PATHS})
    assert path.read_text() == "keep this"
    assert not (root / "results").exists()


def test_submission_requires_real_both_sets(publishing_repo):
    root, _ = publishing_repo
    with pytest.raises(ResultsError, match="both_real_datasets_required"):
        submit(root, {"dev": error_bundle("dev")})
    assert not (root / "results").exists()


def test_push_failure_retains_commit_and_can_retry(publishing_repo):
    root, remote = publishing_repo
    hook = remote / "hooks/pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o700)
    bundles = {k: error_bundle(k) for k in PATHS}
    before = command(root, "rev-parse", "HEAD")
    with pytest.raises(ResultsError, match="git_command_failed_push"):
        submit(root, bundles)
    after = command(root, "rev-parse", "HEAD")
    assert after != before
    assert command(remote, "rev-parse", "main") == before
    hook.unlink()
    assert submit(root, bundles)["remote_sha"] == after


def test_remote_sha_mismatch_not_reported_as_success(publishing_repo, monkeypatch):
    import app.results.submission as module

    root, _ = publishing_repo
    original = module.git

    def wrong_sha(root, *args, **kwargs):
        result = original(root, *args, **kwargs)
        if args[0] == "ls-remote":
            result.stdout = b"0000000000000000000000000000000000000000\trefs/heads/main\n"
        return result

    monkeypatch.setattr(module, "git", wrong_sha)
    with pytest.raises(ResultsError, match="remote_sha_mismatch"):
        submit(root, {k: error_bundle(k) for k in PATHS})


def test_runpod_transfer_verifies_hash_and_cleans_up(tmp_path, monkeypatch):
    import json

    from app.results import runpod

    root = tmp_path / "repository"
    private = root / "backend/data"
    private.mkdir(parents=True)
    (private / "runpod-stage4.ssh_config").write_text("# synthetic SSH config")
    content = b"synthetic snapshot bytes for transport test"
    digest = hashlib.sha256(content).hexdigest()
    calls = []

    def fake_execute(args, *, content=None):
        calls.append(args)
        if args[-1] == "python3 -":
            return json.dumps(
                {"name": "results-export-synthetic.sqlite3", "sha256": digest}
            ).encode()
        if args[0] == "scp":
            Path(args[-1]).write_bytes(b"synthetic snapshot bytes for transport test")
        return b""

    monkeypatch.setattr(runpod, "execute", fake_execute)
    with runpod.runpod_snapshot(root) as path:
        assert path.read_bytes() == content
        assert path.stat().st_mode & 0o777 == 0o600
    assert not path.exists()
    assert calls[-1][-1] == "rm -- /workspace/cqa/backups/results-export-synthetic.sqlite3"


def test_remote_changed_is_not_overwritten(publishing_repo, tmp_path):
    root, remote = publishing_repo
    other = tmp_path / "other"
    command(tmp_path, "clone", "-b", "main", str(remote), str(other))
    command(other, "config", "user.email", "tests@example.invalid")
    command(other, "config", "user.name", "Test")
    (other / "new-work").write_text("someone else")
    command(other, "add", "new-work")
    command(other, "commit", "-m", "other work")
    command(other, "push", "origin", "main")
    remote_sha = command(remote, "rev-parse", "main")
    with pytest.raises(ResultsError, match="remote_main_changed_sync_required"):
        submit(root, {k: error_bundle(k) for k in PATHS})
    assert command(remote, "rev-parse", "main") == remote_sha
    assert not (root / "results").exists()


def test_validation_detects_stale_answers_model_team(export_data):
    app, *_ = export_data
    with app.state.session_factory() as session:
        bundle = exporter(session).build("dev", "DEV")
        for field in ("model", "team_name"):
            doc = copy.deepcopy(bundle.document)
            if field == "model":
                doc[field]["name"] = "invented-model"
            else:
                doc[field] = "other-team"
            with pytest.raises(ResultsError):
                validate_against_bundle(doc, bundle, "dev")
        doc = copy.deepcopy(bundle.document)
        row = next(r for r in doc["results"] if r["status"] == "ok")
        row["criteria"][0]["evidence_turns"] = [1]
        with pytest.raises(ResultsError, match="stale_or_modified"):
            validate_against_bundle(doc, bundle, "dev")

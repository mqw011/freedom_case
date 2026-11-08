"""Export one consistent read-only snapshot; never run inference or mutate evaluations."""

import hashlib
import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.exceptions import DomainError
from app.models import (
    Appeal,
    AppealDecision,
    Checklist,
    ChecklistVersion,
    Conversation,
    Dataset,
    Evaluation,
)
from app.models.ai import AIJob
from app.results.contract import COUNTS, IDS, ResultsError, validate
from app.results.privacy import public_rationale
from app.schemas.checklists import CriterionConfig
from app.seed.default_checklist import SEED_KEY, default_checklist
from app.services.evaluation_service import EvaluationService
from app.services.evidence_validator import EvidenceValidator


@contextmanager
def snapshot_session(database):
    source = Path(database).resolve()
    if not source.is_file():
        raise ResultsError("database_not_found")
    with tempfile.TemporaryDirectory(prefix="cqa-export-") as directory:
        snapshot = Path(directory) / "snapshot.sqlite3"
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src:
            with sqlite3.connect(snapshot) as dst:
                src.backup(dst, pages=256, sleep=0.05)
                if dst.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise ResultsError("database_integrity_failed")
                if dst.execute("PRAGMA foreign_key_check").fetchone():
                    raise ResultsError("database_foreign_keys_failed")
        digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        engine = create_engine(
            "sqlite://", creator=lambda: sqlite3.connect(snapshot.as_uri() + "?mode=ro", uri=True)
        )
        try:
            with Session(engine, autoflush=False) as session:
                yield session, digest
        finally:
            engine.dispose()


def compatible(version):
    actual = {c.code: CriterionConfig.model_validate(c) for c in version.criteria}
    expected = {c.code: c for c in default_checklist().version.criteria}
    fields = ("criterion_type", "weight", "allowed_values", "max_score", "allow_na")
    return set(actual) == set(expected) and all(
        all(getattr(actual[code], field) == getattr(config, field) for field in fields)
        for code, config in expected.items()
    )


def turns_for(evidence, messages, validator, conversation_id):
    by_id = {m.id: m for m in messages}
    turns = set()
    for item in evidence:
        validator.validate(conversation_id, item)
        if item.message_id is None or item.message_id not in by_id:
            raise ResultsError("invalid_evidence")
        start = by_id[item.message_id].message_index
        end = start if item.end_message_id is None else by_id[item.end_message_id].message_index
        turns.update(range(start + 1, end + 2))
    return sorted(turns)


@dataclass
class ExportBundle:
    document: dict
    expected_turns: dict
    provenance: list


class ResultsExporter:
    def __init__(self, session, *, team_name, model_mode, fallback_model):
        self.session = session
        self.team_name = team_name
        self.model_mode = model_mode
        self.fallback_model = fallback_model

    def version(self, version_id):
        if version_id is None:
            checklist = self.session.scalar(select(Checklist).where(Checklist.seed_key == SEED_KEY))
            version_id = checklist.active_version_id if checklist else None
        version = self.session.get(ChecklistVersion, version_id) if version_id else None
        if version is None or not compatible(version):
            raise ResultsError("checklist_incompatible_with_official_1_0")
        return version

    def build(self, kind, group_id, *, version_id=None):
        if kind == "prod" and (not group_id or group_id == "DEV"):
            raise ResultsError("real_control_group_required")
        dataset = self.session.scalar(select(Dataset).where(Dataset.group_id == group_id))
        if dataset is None:
            raise ResultsError("dataset_not_imported")
        conversations = list(
            self.session.scalars(
                select(Conversation)
                .where(Conversation.dataset_id == dataset.id)
                .order_by(Conversation.id)
            )
        )
        if len(conversations) != COUNTS[kind] or dataset.total_records != len(conversations):
            raise ResultsError("dataset_count_mismatch")
        calls = sum(c.channel == "voice call" for c in conversations)
        if calls != (5 if kind == "dev" else 0):
            raise ResultsError("dataset_channels_mismatch")
        version = self.version(version_id)
        jobs = list(
            self.session.scalars(
                select(AIJob)
                .where(
                    AIJob.conversation_id.in_([c.id for c in conversations]),
                    AIJob.checklist_version_id == version.id,
                )
                .order_by(AIJob.created_at.desc(), AIJob.id.desc())
            )
        )
        latest = {}
        for job in jobs:
            latest.setdefault(job.conversation_id, job)
        records, provenance, models = [], [], set()
        bounds = {}
        for conversation in conversations:
            messages = conversation.messages
            if [m.message_index for m in messages] != list(range(len(messages))) or not messages:
                raise ResultsError("transcript_order_invalid")
            bounds[conversation.conversation_id] = len(messages)
            job = latest.get(conversation.id)
            if job:
                models.add(job.model)
            metadata = {
                "conversation_id": conversation.conversation_id,
                "job_id": job.id if job else None,
                "checklist_version_id": version.id,
            }
            if job is None or job.status != "completed":
                reasons = {
                    "queued": "Оценка ещё в очереди.",
                    "running": "Оценка ещё выполняется.",
                    "failed": "Оценка не прошла обработку или проверку.",
                    "cancelled": "Задание оценки отменено.",
                }
                record = self.error(
                    conversation,
                    reasons.get(
                        job.status if job else None, "AI-оценка по выбранной версии ещё не создана."
                    ),
                )
            else:
                try:
                    record, revision = self.completed(conversation, job, version)
                    metadata.update(evaluation_id=job.evaluation_id, revision=revision)
                except (ResultsError, DomainError, ValueError, KeyError):
                    # A damaged evaluation is retained as an error, never hidden or scored zero.
                    record = self.error(
                        conversation, "Сохранённая оценка не прошла проверку экспорта."
                    )
            records.append(record)
            provenance.append(metadata)
        document = {
            "schema_version": "1.0",
            "team_name": self.team_name,
            "model": {
                "mode": self.model_mode,
                "name": ", ".join(sorted(models)) if models else self.fallback_model,
            },
            "results": records,
        }
        validate(document, kind=kind, expected_turns=bounds)
        return ExportBundle(document, bounds, provenance)

    @staticmethod
    def error(conversation, reason):
        return {
            "conversation_id": conversation.conversation_id,
            "status": "error",
            "criteria": [],
            "score": None,
            "error": reason,
        }

    def completed(self, conversation, job, version):
        evaluation = self.session.get(Evaluation, job.evaluation_id)
        if (
            evaluation is None
            or evaluation.status != "completed"
            or evaluation.source != "ai"
            or evaluation.conversation_id != conversation.id
            or evaluation.checklist_version_id != version.id
        ):
            raise ResultsError("evaluation_provenance_invalid")
        detail = EvaluationService(self.session).detail(evaluation)
        # Detail reuses the official Decimal engine and includes accepted appeal decisions.
        current = {r.criterion_code: r for r in detail.results}
        if len(current) != 8 or set(current) != set(IDS):
            raise ResultsError("criterion_ids_mismatch")
        revisions = dict(
            self.session.execute(
                select(Appeal.criterion_result_id, AppealDecision.reason)
                .join(AppealDecision, AppealDecision.appeal_id == Appeal.id)
                .where(Appeal.evaluation_id == evaluation.id, AppealDecision.decision == "revised")
                .order_by(AppealDecision.id)
            ).all()
        )
        validator = EvidenceValidator(self.session)
        criteria = []
        for code, name in IDS.items():
            result = current[code]
            answer = result.current_answer
            if isinstance(answer, Decimal):
                if answer != answer.to_integral_value():
                    raise ResultsError("invalid_scale_step")
                value = int(answer)
            else:
                value = {"yes": True, "no": False, "na": None}[answer]
            rationale = revisions.get(result.id, result.explanation)
            criteria.append(
                {
                    "criterion_id": name,
                    "value": value,
                    "rationale": public_rationale(
                        rationale, [m.text for m in conversation.messages]
                    ),
                    "evidence_turns": turns_for(
                        result.evidence, conversation.messages, validator, conversation.id
                    ),
                }
            )
        row = {
            "conversation_id": conversation.conversation_id,
            "status": "ok",
            "criteria": criteria,
            "score": {
                "final_score": detail.final_score,
                "critical_flag": detail.critical_violation,
            },
        }
        # Check persisted final_score/critical_flag, not a replacement calculated by the exporter.
        validate(
            {
                "schema_version": "1.0",
                "team_name": self.team_name,
                "model": {"mode": self.model_mode, "name": job.model},
                "results": [row],
            },
            expected_turns={conversation.conversation_id: len(conversation.messages)},
        )
        return row, detail.revision


def validate_against_bundle(document, bundle, kind, *, require_complete=False):
    report = validate(
        document, kind=kind, expected_turns=bundle.expected_turns, require_complete=require_complete
    )
    # Compare by ID; array ordering is not part of the official contract.
    expected = {r["conversation_id"]: r for r in bundle.document["results"]}
    for record in document["results"]:
        actual = dict(record)
        if actual["status"] == "ok":
            actual["criteria"] = sorted(actual["criteria"], key=lambda c: c["criterion_id"])
        original = dict(expected[record["conversation_id"]])
        if original["status"] == "ok":
            original["criteria"] = sorted(original["criteria"], key=lambda c: c["criterion_id"])
        if actual != original:
            raise ResultsError("stale_or_modified_results_reexport_required")
    if document["model"] != bundle.document["model"]:
        raise ResultsError("model_provenance_mismatch")
    if document["team_name"] != bundle.document["team_name"]:
        raise ResultsError("team_name_mismatch")
    return report

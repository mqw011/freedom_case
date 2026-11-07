import hashlib
import json
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.ai.exceptions import SAFE_MESSAGES
from app.ai.prompt_engine import PROMPT_VERSION
from app.core.config import Settings
from app.core.database import utcnow
from app.core.exceptions import DomainError
from app.models import Checklist, ChecklistVersion, Conversation, Dataset
from app.models.ai import AIBatch, AIJob, AIJobAttempt, AIWorkerLease
from app.schemas.ai import AIBatchCreate, AIBatchRead, AIJobCreate
from app.services.checklist_service import ChecklistService
from app.services.common import require

PINNED_SETTINGS = (
    "llm_temperature",
    "llm_timeout",
    "llm_max_retries",
    "llm_retry_delay",
    "llm_context_length",
    "llm_max_output_tokens",
    "llm_response_mode",
    "llm_think",
    "llm_seed",
    "ai_max_repairs",
    "ai_chunk_overlap",
    "ai_max_chunks",
    "ai_explanation_language",
    "ai_semantic_review",
)


def fingerprint(data) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class JobService:
    def __init__(self, session: Session, settings: Settings):
        self.session = session
        self.settings = settings

    def _enabled(self):
        if not self.settings.ai_job_enabled:
            raise DomainError(503, "ai_disabled", "AI job submission is disabled")

    def resolve_version(self, version_id=None, checklist_id=None):
        if version_id is not None:
            version = require(self.session, ChecklistVersion, version_id)
            if checklist_id is not None and version.checklist_id != checklist_id:
                raise DomainError(422, "version_mismatch", "Version belongs to another checklist")
        else:
            checklist = (
                require(self.session, Checklist, checklist_id)
                if checklist_id
                else self.session.scalar(
                    select(Checklist).where(Checklist.seed_key == "freedom-broker-original-v1")
                )
            )
            if checklist is None or checklist.active_version_id is None:
                raise DomainError(422, "no_active_version", "No active checklist version")
            version = require(self.session, ChecklistVersion, checklist.active_version_id)
        ChecklistService.validate_weights(version)
        return version

    def _job(self, conversation_id, version_id, request_hash, *, batch_id=None, key=None):
        return AIJob(
            conversation_id=conversation_id,
            checklist_version_id=version_id,
            batch_id=batch_id,
            request_hash=request_hash,
            idempotency_key=key,
            model=self.settings.llm_model,
            provider=self.settings.llm_provider,
            max_attempts=self.settings.ai_job_max_attempts,
            inference_config={
                **{k: getattr(self.settings, k) for k in PINNED_SETTINGS},
                "prompt_version": PROMPT_VERSION,
            },
        )

    def create(self, request: AIJobCreate) -> AIJob:
        self._enabled()
        request_hash = fingerprint(request.model_dump(mode="json", exclude={"idempotency_key"}))
        if request.idempotency_key:
            existing = self.session.scalar(
                select(AIJob).where(AIJob.idempotency_key == request.idempotency_key)
            )
            if existing:
                if existing.request_hash != request_hash:
                    raise DomainError(
                        409, "idempotency_conflict", "Key was used with different input"
                    )
                return existing
        require(self.session, Conversation, request.conversation_id)
        version = self.resolve_version(request.checklist_version_id, request.checklist_id)
        job = self._job(
            request.conversation_id, version.id, request_hash, key=request.idempotency_key
        )
        self.session.add(job)
        self.session.flush()
        return job

    def create_batch(self, request: AIBatchCreate) -> AIBatch:
        self._enabled()
        request_hash = fingerprint(request.model_dump(mode="json", exclude={"idempotency_key"}))
        if request.idempotency_key:
            existing = self.session.scalar(
                select(AIBatch).where(AIBatch.idempotency_key == request.idempotency_key)
            )
            if existing:
                if existing.request_hash != request_hash:
                    raise DomainError(
                        409, "idempotency_conflict", "Key was used with different input"
                    )
                return existing
        statement = select(Conversation.id).order_by(Conversation.id)
        if request.conversation_ids is not None:
            statement = statement.where(Conversation.id.in_(request.conversation_ids))
        else:
            if request.dataset_id:
                require(self.session, Dataset, request.dataset_id)
                statement = statement.where(Conversation.dataset_id == request.dataset_id)
            if request.language:
                statement = statement.where(Conversation.language == request.language)
            if request.channel:
                statement = statement.where(Conversation.channel == request.channel)
        ids = list(self.session.scalars(statement.limit(10001)))
        if not ids or len(ids) > 10000:
            raise DomainError(
                422, "invalid_batch_size", "Batch must select 1 to 10000 conversations"
            )
        if request.conversation_ids is not None and set(ids) != set(request.conversation_ids):
            raise DomainError(404, "not_found", "Some conversations do not exist")
        version = self.resolve_version(request.checklist_version_id, request.checklist_id)
        batch = AIBatch(
            checklist_version_id=version.id,
            idempotency_key=request.idempotency_key,
            request_hash=request_hash,
        )
        self.session.add(batch)
        self.session.flush()
        self.session.add_all(
            [self._job(i, version.id, request_hash, batch_id=batch.id) for i in ids]
        )
        self.session.flush()
        return batch

    def batch_detail(self, batch: AIBatch) -> AIBatchRead:
        counts = dict(
            self.session.execute(
                select(AIJob.status, func.count(AIJob.id))
                .where(AIJob.batch_id == batch.id)
                .group_by(AIJob.status)
            ).all()
        )
        total = sum(counts.values())
        terminal = sum(counts.get(s, 0) for s in ("completed", "failed", "cancelled"))
        return AIBatchRead(
            id=batch.id,
            checklist_version_id=batch.checklist_version_id,
            created_at=batch.created_at,
            total=total,
            **{
                s: counts.get(s, 0)
                for s in ("queued", "running", "completed", "failed", "cancelled")
            },
            percentage=(Decimal(terminal) * 100 / total).quantize(Decimal("0.01"))
            if total
            else Decimal(0),
        )

    def cancel(self, job_id: int) -> AIJob:
        job = require(self.session, AIJob, job_id)
        if job.status not in {"queued", "running"}:
            raise DomainError(409, "job_terminal", "Only queued/running jobs can be cancelled")
        now = utcnow()
        if job.status == "queued":
            result = self.session.execute(
                update(AIJob)
                .where(AIJob.id == job_id, AIJob.status == "queued")
                .values(status="cancelled", completed_at=now, cancel_requested=True)
            )
        else:
            result = self.session.execute(
                update(AIJob)
                .where(AIJob.id == job_id, AIJob.status == "running")
                .values(cancel_requested=True)
            )
        if result.rowcount != 1:
            raise DomainError(409, "job_changed", "Refresh job state and retry")
        self.session.expire(job)
        return job

    def retry(self, job_id: int) -> AIJob:
        self._enabled()
        job = require(self.session, AIJob, job_id)
        if job.status != "failed":
            raise DomainError(409, "job_not_failed", "Only failed jobs can be retried")
        self.session.execute(
            update(AIJob)
            .where(AIJob.id == job.id, AIJob.status == "failed")
            .values(
                status="queued",
                max_attempts=job.attempts + self.settings.ai_job_max_attempts,
                completed_at=None,
                error_code=None,
                safe_error_message=None,
                owner=None,
                claim_token=None,
                lease_expires_at=None,
                cancel_requested=False,
                next_attempt_at=utcnow(),
            )
        )
        self.session.expire(job)
        return job


def acquire_worker(session: Session, owner: str, settings: Settings) -> bool:
    now = utcnow()
    result = session.execute(
        update(AIWorkerLease)
        .where(
            AIWorkerLease.id == 1,
            or_(
                AIWorkerLease.owner == owner,
                AIWorkerLease.expires_at.is_(None),
                AIWorkerLease.expires_at < now,
            ),
        )
        .values(
            owner=owner,
            heartbeat_at=now,
            expires_at=now + timedelta(seconds=settings.ai_lease_seconds),
            concurrency=settings.llm_max_concurrency,
        )
    )
    return result.rowcount == 1


def recover_expired(session: Session):
    now = utcnow()
    # Called under the singleton worker write lease, preventing simultaneous recovery/claim.
    jobs = session.scalars(
        select(AIJob).where(AIJob.status == "running", AIJob.lease_expires_at < now)
    ).all()
    for job in jobs:
        terminal = job.cancel_requested or job.attempts >= job.max_attempts
        job.status = "cancelled" if job.cancel_requested else "failed" if terminal else "queued"
        job.error_code = "cancelled" if job.cancel_requested else "lease_expired"
        job.safe_error_message = SAFE_MESSAGES[job.error_code]
        job.completed_at = now if terminal else None
        job.owner = job.claim_token = job.lease_expires_at = None
        job.next_attempt_at = now
        session.execute(
            update(AIJobAttempt)
            .where(AIJobAttempt.job_id == job.id, AIJobAttempt.attempt_number == job.attempts)
            .values(status="interrupted", error_code="lease_expired", finished_at=now)
        )


def claim_job(session: Session, owner: str, settings: Settings) -> AIJob | None:
    now = utcnow()
    candidate = (
        select(AIJob.id)
        .where(
            AIJob.status == "queued",
            AIJob.next_attempt_at <= now,
            AIJob.attempts < AIJob.max_attempts,
        )
        .order_by(AIJob.id)
        .limit(1)
        .scalar_subquery()
    )
    lease = (
        select(AIWorkerLease.id)
        .where(AIWorkerLease.id == 1, AIWorkerLease.owner == owner, AIWorkerLease.expires_at > now)
        .exists()
    )
    job_id = session.scalar(
        update(AIJob)
        .where(AIJob.id == candidate, AIJob.status == "queued", lease)
        .values(
            status="running",
            owner=owner,
            claim_token=uuid4().hex,
            attempts=AIJob.attempts + 1,
            started_at=now,
            completed_at=None,
            error_code=None,
            safe_error_message=None,
            lease_expires_at=now + timedelta(seconds=settings.ai_lease_seconds),
        )
        .returning(AIJob.id)
    )
    if job_id is None:
        return None
    job = session.get(AIJob, job_id)
    session.add(AIJobAttempt(job_id=job.id, attempt_number=job.attempts))
    session.flush()
    return job

from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime, utcnow


class AIBatch(Base):
    __tablename__ = "ai_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    checklist_version_id: Mapped[int] = mapped_column(ForeignKey("checklist_versions.id"))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class AIJob(Base):
    __tablename__ = "ai_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    checklist_version_id: Mapped[int] = mapped_column(
        ForeignKey("checklist_versions.id"), index=True
    )
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("ai_batches.id"), index=True)
    evaluation_id: Mapped[int | None] = mapped_column(ForeignKey("evaluations.id"), unique=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(200))
    provider: Mapped[str] = mapped_column(String(40))
    inference_config: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=2)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    owner: Mapped[str | None] = mapped_column(String(64))
    claim_token: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    error_code: Mapped[str | None] = mapped_column(String(80))
    safe_error_message: Mapped[str | None] = mapped_column(String(300))
    diagnostics: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','completed','failed','cancelled')"),
        CheckConstraint("attempts >= 0 AND max_attempts > 0"),
        UniqueConstraint("batch_id", "conversation_id"),
    )


class AIJobAttempt(Base):
    __tablename__ = "ai_job_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("ai_jobs.id"), index=True)
    attempt_number: Mapped[int] = mapped_column()
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(20), default="running")
    error_code: Mapped[str | None] = mapped_column(String(80))
    diagnostics: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("job_id", "attempt_number"),)


class AIWorkerLease(Base):
    __tablename__ = "ai_worker_lease"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str | None] = mapped_column(String(64))
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    concurrency: Mapped[int] = mapped_column(default=1)
    __table_args__ = (CheckConstraint("id = 1"),)

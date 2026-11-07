from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from app.schemas.common import PositiveId, Schema
from app.schemas.datasets import Channel, Language

IdempotencyKey = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]
JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


class AIJobCreate(Schema):
    conversation_id: PositiveId
    checklist_version_id: PositiveId | None = None
    checklist_id: PositiveId | None = None
    idempotency_key: IdempotencyKey | None = None


class AIBatchCreate(Schema):
    conversation_ids: list[PositiveId] | None = Field(default=None, min_length=1, max_length=10000)
    dataset_id: PositiveId | None = None
    language: Language | None = None
    channel: Channel | None = None
    checklist_version_id: PositiveId | None = None
    checklist_id: PositiveId | None = None
    idempotency_key: IdempotencyKey | None = None

    @model_validator(mode="after")
    def selector(self):
        if (
            self.conversation_ids is None
            and self.dataset_id is None
            and self.language is None
            and self.channel is None
        ):
            raise ValueError("Choose conversation IDs, dataset or filters")
        if self.conversation_ids is not None:
            if len(set(self.conversation_ids)) != len(self.conversation_ids):
                raise ValueError("Duplicate conversation IDs")
            if any(v is not None for v in (self.dataset_id, self.language, self.channel)):
                raise ValueError("Explicit IDs cannot be combined with filters")
        return self


class AIJobRead(Schema):
    id: int
    conversation_id: int
    checklist_version_id: int
    batch_id: int | None
    evaluation_id: int | None
    provider: str
    model: str
    status: JobStatus
    attempts: int
    max_attempts: int
    cancel_requested: bool
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    next_attempt_at: datetime
    error_code: str | None
    safe_error_message: str | None
    diagnostics: dict


class AIJobAttemptRead(Schema):
    attempt_number: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    error_code: str | None
    diagnostics: dict


class AIBatchRead(Schema):
    id: int
    checklist_version_id: int
    created_at: datetime
    total: int
    queued: int
    running: int
    completed: int
    failed: int
    cancelled: int
    percentage: Decimal


class RetryBatchRead(Schema):
    batch_id: int
    retried: int


class ProviderHealth(Schema):
    available: bool
    model: str
    error_code: str | None


class WorkerHealth(Schema):
    available: bool
    heartbeat_at: datetime | None
    lease_expires_at: datetime | None
    concurrency: int


class AIHealth(Schema):
    enabled: bool
    provider: ProviderHealth
    worker: WorkerHealth

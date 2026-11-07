from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.checklists import Answer
from app.schemas.common import NonEmpty, PositiveId, Schema


class EvidenceInput(Schema):
    evidence_type: Literal["quote", "range", "absence"]
    message_id: PositiveId | None = None
    end_message_id: PositiveId | None = None
    excerpt: NonEmpty | None = None
    explanation: NonEmpty

    @model_validator(mode="after")
    def shape(self):
        if self.evidence_type == "quote":
            if self.message_id is None or self.excerpt is None or self.end_message_id is not None:
                raise ValueError("Quote requires one message and an excerpt")
        if self.evidence_type == "range":
            if self.message_id is None or self.end_message_id is None:
                raise ValueError("Range requires start and end messages")
        if self.end_message_id is not None and self.message_id is None:
            raise ValueError("An end message requires a start message")
        if self.excerpt is not None and self.message_id is None:
            raise ValueError("An excerpt requires a message")
        return self


class StructuredCriterionResult(Schema):
    criterion_code: NonEmpty = Field(max_length=40)
    answer: Answer
    explanation: NonEmpty
    evidence: list[EvidenceInput] = Field(default_factory=list, max_length=100)


class EvaluationSubmission(Schema):
    conversation_id: PositiveId
    checklist_version_id: PositiveId
    source: Literal["manual", "test", "ai"] = "manual"
    results: list[StructuredCriterionResult] = Field(min_length=1, max_length=100)


class EvaluationCreate(EvaluationSubmission):
    """Public Stage 1 endpoint accepts only manual/test submissions."""

    source: Literal["manual", "test"] = "manual"


class EvidenceRead(EvidenceInput):
    id: int
    criterion_result_id: int


class CriterionResultRead(Schema):
    id: int
    evaluation_id: int
    criterion_id: int
    criterion_code: str
    answer: Answer
    raw_score: Decimal | None
    weighted_score: Decimal | None
    is_na: bool
    explanation: str
    created_at: datetime
    current_answer: Answer
    current_raw_score: Decimal | None
    current_weighted_score: Decimal | None
    current_is_na: bool
    evidence: list[EvidenceRead]


class EvaluationRead(Schema):
    id: int
    conversation_id: int
    checklist_version_id: int
    status: str
    source: str
    initial_score: Decimal | None
    final_score: Decimal | None
    initial_critical_violation: bool
    critical_violation: bool
    revision: int
    created_at: datetime
    completed_at: datetime | None


class EvaluationDetail(EvaluationRead):
    results: list[CriterionResultRead]
    appeal_ids: list[int]

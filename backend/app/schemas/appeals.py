from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import model_validator

from app.schemas.checklists import Answer
from app.schemas.common import NonEmpty, PositiveId, Schema


class AppealCreate(Schema):
    criterion_result_id: PositiveId
    comment: NonEmpty


class DecisionCreate(Schema):
    decision: Literal["upheld", "revised"]
    revised_answer: Answer | None = None
    reason: NonEmpty

    @model_validator(mode="after")
    def revision_answer(self):
        if (self.decision == "revised") != (self.revised_answer is not None):
            raise ValueError("Only revised decisions require revised_answer")
        return self


class DecisionRead(Schema):
    id: int
    appeal_id: int
    decision: str
    original_answer: Answer
    revised_answer: Answer
    original_score: Decimal | None
    revised_score: Decimal | None
    original_final_score: Decimal | None
    revised_final_score: Decimal | None
    reason: str
    decided_at: datetime


class AppealRead(Schema):
    id: int
    evaluation_id: int
    criterion_result_id: int
    comment: str
    status: str
    created_at: datetime
    decision: DecisionRead | None

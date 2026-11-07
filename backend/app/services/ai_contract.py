"""Stage 2 integration boundary. Deliberately contains no inference implementation."""

from typing import Protocol

from pydantic import Field

from app.schemas.checklists import VersionRead
from app.schemas.common import Schema
from app.schemas.datasets import ConversationDetail
from app.schemas.evaluations import StructuredCriterionResult


class EvaluationContext(Schema):
    conversation: ConversationDetail
    checklist_version: VersionRead


class StructuredEvaluation(Schema):
    results: list[StructuredCriterionResult] = Field(min_length=1, max_length=100)


class AIEvaluator(Protocol):
    async def evaluate(self, context: EvaluationContext) -> StructuredEvaluation:
        """Return grounded results; adapter owns retries, chunking and model transport.

        Use StructuredEvaluation.model_json_schema() for constrained JSON output.
        Persist only after EvidenceValidator and ScoringEngine accept the result.
        """
        ...

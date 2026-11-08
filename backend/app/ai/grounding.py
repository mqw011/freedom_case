from decimal import Decimal

from app.ai.exceptions import GroundingError
from app.ai.prompt_engine import ChunkReview
from app.schemas.checklists import CriterionConfig
from app.schemas.evaluations import EvidenceInput
from app.services.ai_contract import EvaluationContext, StructuredEvaluation
from app.services.scoring_engine import ScoringError, score


def validate_evidence(context: EvaluationContext, evidence: EvidenceInput, visible_ids: set[int]):
    messages = {m.id: m for m in context.conversation.messages}
    ids = [i for i in (evidence.message_id, evidence.end_message_id) if i is not None]
    if not ids or any(i not in messages or i not in visible_ids for i in ids):
        raise GroundingError("invalid_evidence", hint="Use only supplied internal message IDs.")
    if evidence.message_id is None:
        raise GroundingError("invalid_evidence", hint="Evidence needs a start message ID.")
    start = messages[evidence.message_id]
    end = messages[evidence.end_message_id] if evidence.end_message_id is not None else start
    if start.message_index > end.message_index:
        raise GroundingError("invalid_evidence", hint="Range start must precede its end.")
    # A range cannot claim to cover messages that were never supplied to any reviewed window.
    range_ids = {
        m.id
        for m in context.conversation.messages
        if start.message_index <= m.message_index <= end.message_index
    }
    if not range_ids <= visible_ids:
        raise GroundingError("coverage_incomplete")
    if evidence.excerpt is not None and evidence.excerpt not in start.text:
        raise GroundingError(
            "invalid_evidence",
            hint=(
                f"Copy an EXACT substring from message ID {start.id}, "
                "preserving punctuation and spelling."
            ),
        )
    if evidence.evidence_type == "absence" and evidence.end_message_id is None:
        raise GroundingError("invalid_evidence", hint="Absence needs both start and end IDs.")


def validate_grounding(
    context: EvaluationContext,
    output: StructuredEvaluation,
    covered_ids: set[int],
    *,
    codes: set[str] | None = None,
):
    all_ids = {m.id for m in context.conversation.messages}
    if covered_ids != all_ids:
        raise GroundingError("coverage_incomplete")
    criteria = [
        CriterionConfig.model_validate(c)
        for c in context.checklist_version.criteria
        if codes is None or c.code in codes
    ]
    try:
        score(criteria, [(r.criterion_code, r.answer) for r in output.results])
    except ScoringError:
        raise GroundingError("invalid_answers") from None
    for result in output.results:
        if not result.evidence:
            raise GroundingError(
                "invalid_evidence",
                criteria=(result.criterion_code,),
                hint="Every result needs at least one evidence item with real message IDs.",
            )
        if result.answer == "yes" and not any(e.evidence_type == "quote" for e in result.evidence):
            raise GroundingError(
                "invalid_evidence",
                criteria=(result.criterion_code,),
                hint=(
                    "A yes answer requires at least one evidence_type=quote with an EXACT "
                    "source excerpt and end_message_id=null. A range alone is insufficient."
                ),
            )
        if (
            isinstance(result.answer, Decimal)
            and result.answer > 0
            and not any(e.evidence_type in {"quote", "range"} for e in result.evidence)
        ):
            raise GroundingError(
                "invalid_evidence",
                criteria=(result.criterion_code,),
                hint="A positive scale answer requires a quote or range, not only absence.",
            )
        for evidence in result.evidence:
            try:
                validate_evidence(context, evidence, covered_ids)
            except GroundingError as exc:
                raise GroundingError(
                    exc.code, criteria=(result.criterion_code,), hint=exc.hint
                ) from None


def validate_chunk(context: EvaluationContext, review: ChunkReview, window_ids: set[int]):
    if len(review.covered_message_ids) != len(
        set(review.covered_message_ids)
    ) or review.covered_message_ids != [
        m.id for m in context.conversation.messages if m.id in window_ids
    ]:
        raise GroundingError("coverage_incomplete")
    expected = {c.code for c in context.checklist_version.criteria}
    actual = [f.criterion_code for f in review.facts]
    if set(actual) != expected or len(actual) != len(expected):
        raise GroundingError("invalid_answers")
    for fact in review.facts:
        for evidence in fact.evidence:
            validate_evidence(context, evidence, window_ids)

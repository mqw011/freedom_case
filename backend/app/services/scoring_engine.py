"""Pure deterministic scoring. No ORM, HTTP or AI dependencies; no criterion-code rules."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext

from app.schemas.checklists import Answer, CriterionConfig


class ScoringError(ValueError):
    pass


@dataclass(frozen=True)
class ScoredCriterion:
    code: str
    answer: Answer
    raw_score: Decimal | None
    weighted_score: Decimal | None
    is_na: bool


@dataclass(frozen=True)
class ScoringResult:
    results: tuple[ScoredCriterion, ...]
    earned_total: Decimal
    applicable_weight: Decimal
    final_score: Decimal | None
    critical_violation: bool


def score_criterion(criterion: CriterionConfig, answer: Answer) -> ScoredCriterion:
    if answer == "na":
        if not criterion.allow_na:
            raise ScoringError(f"Criterion {criterion.code} does not allow N/A")
        return ScoredCriterion(criterion.code, answer, None, None, True)
    if criterion.criterion_type in {"binary", "flag"}:
        if answer not in ("yes", "no"):
            raise ScoringError(f"Criterion {criterion.code} requires yes/no")
        raw = Decimal(1) if answer == "yes" else Decimal(0)
    else:
        if not isinstance(answer, Decimal) or answer not in criterion.allowed_values:
            raise ScoringError(f"Criterion {criterion.code} requires an allowed scale value")
        raw = answer
    with localcontext() as context:
        context.prec = 50
        weighted = raw / criterion.max_score * criterion.weight
    return ScoredCriterion(criterion.code, answer, raw, weighted, False)


def score(criteria: list[CriterionConfig], answers: list[tuple[str, Answer]]) -> ScoringResult:
    config_codes = [c.code for c in criteria]
    answer_codes = [code for code, _ in answers]
    if len(config_codes) != len(set(config_codes)):
        raise ScoringError("Duplicate criterion configuration")
    if len(answer_codes) != len(set(answer_codes)):
        raise ScoringError("Duplicate criterion result")
    if set(answer_codes) != set(config_codes):
        raise ScoringError("Results must include every criterion exactly once, including flags")
    by_code = dict(answers)
    with localcontext() as context:
        context.prec = 50
        results = tuple(score_criterion(c, by_code[c.code]) for c in criteria)
        applicable_weight = sum(
            (c.weight for c, r in zip(criteria, results, strict=True) if not r.is_na), Decimal(0)
        )
        earned_total = sum((r.weighted_score or Decimal(0) for r in results), Decimal(0))
        final = (
            None
            if not applicable_weight
            else (earned_total / applicable_weight * Decimal(100)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        )
    violation = any(c.criterion_type == "flag" and by_code[c.code] == "yes" for c in criteria)
    return ScoringResult(results, earned_total, applicable_weight, final, violation)

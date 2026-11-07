from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import DomainError
from app.models import Appeal, AppealDecision, ChecklistVersion, CriterionResult, Evaluation
from app.schemas.appeals import AppealCreate, DecisionCreate
from app.services.checklist_service import ChecklistService
from app.services.common import require
from app.services.evaluation_service import EvaluationService


class AppealService:
    def __init__(self, session: Session):
        self.session = session

    def create(self, evaluation_id: int, data: AppealCreate) -> Appeal:
        require(self.session, Evaluation, evaluation_id)
        result = require(self.session, CriterionResult, data.criterion_result_id)
        if result.evaluation_id != evaluation_id:
            raise DomainError(
                422, "result_mismatch", "Criterion result belongs to another evaluation"
            )
        existing = self.session.scalar(
            select(Appeal.id).where(Appeal.pending_result_id == result.id)
        )
        if existing is not None:
            raise DomainError(409, "appeal_pending", "This criterion already has an open appeal")
        appeal = Appeal(
            evaluation_id=evaluation_id,
            criterion_result_id=result.id,
            pending_result_id=result.id,
            comment=data.comment,
        )
        self.session.add(appeal)
        self.session.flush()
        return appeal

    def decide(self, appeal_id: int, data: DecisionCreate) -> Appeal:
        appeal = require(self.session, Appeal, appeal_id)
        if appeal.status != "pending":
            raise DomainError(409, "appeal_closed", "This appeal has already been decided")
        evaluation = require(self.session, Evaluation, appeal.evaluation_id)
        result = require(self.session, CriterionResult, appeal.criterion_result_id)
        version = require(self.session, ChecklistVersion, evaluation.checklist_version_id)
        evaluations = EvaluationService(self.session)
        answers = evaluations.current_answers(evaluation)
        configs = ChecklistService.configs(version)
        original_answer = answers[result.criterion_id]
        before = evaluations.calculate(configs, [(c.code, answers[c.id]) for c in version.criteria])
        if data.decision == "revised":
            if data.revised_answer == original_answer:
                raise DomainError(
                    422, "unchanged_answer", "Use upheld when the answer is unchanged"
                )
            answers[result.criterion_id] = data.revised_answer
        after = evaluations.calculate(configs, [(c.code, answers[c.id]) for c in version.criteria])
        code = next(c.code for c in version.criteria if c.id == result.criterion_id)
        previous = next(r for r in before.results if r.code == code)
        revised = next(r for r in after.results if r.code == code)
        decision = AppealDecision(
            appeal_id=appeal.id,
            decision=data.decision,
            original_answer=str(original_answer),
            revised_answer=str(answers[result.criterion_id]),
            original_score=previous.weighted_score,
            revised_score=revised.weighted_score,
            original_final_score=evaluation.final_score,
            revised_final_score=after.final_score,
            reason=data.reason,
        )
        self.session.add(decision)
        appeal.status = data.decision
        appeal.pending_result_id = None
        appeal.decision = decision
        evaluation.final_score = after.final_score
        evaluation.critical_violation = after.critical_violation
        # Serialize concurrent decisions, even if only a zero-weight flag changed.
        evaluation.revision += 1
        self.session.flush()
        return appeal

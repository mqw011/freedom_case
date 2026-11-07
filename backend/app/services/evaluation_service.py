from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.core.exceptions import DomainError
from app.models import (
    Appeal,
    AppealDecision,
    ChecklistVersion,
    Conversation,
    CriterionResult,
    Evaluation,
    Evidence,
)
from app.schemas.checklists import CriterionConfig
from app.schemas.evaluations import CriterionResultRead, EvaluationDetail, EvaluationSubmission
from app.services.checklist_service import ChecklistService
from app.services.common import require
from app.services.evidence_validator import EvidenceValidator
from app.services.scoring_engine import ScoringError, score


class EvaluationService:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def calculate(criteria, answers):
        try:
            return score(criteria, answers)
        except ScoringError as exc:
            raise DomainError(422, "invalid_results", str(exc)) from exc

    def create(self, data: EvaluationSubmission) -> Evaluation:
        require(self.session, Conversation, data.conversation_id)
        version = require(self.session, ChecklistVersion, data.checklist_version_id)
        ChecklistService.validate_weights(version)
        calculation = self.calculate(
            ChecklistService.configs(version), [(r.criterion_code, r.answer) for r in data.results]
        )
        validator = EvidenceValidator(self.session)
        for result in data.results:
            for evidence in result.evidence:
                validator.validate(data.conversation_id, evidence)
        evaluation = Evaluation(
            conversation_id=data.conversation_id,
            checklist_version_id=version.id,
            source=data.source,
            initial_score=calculation.final_score,
            final_score=calculation.final_score,
            critical_violation=calculation.critical_violation,
            initial_critical_violation=calculation.critical_violation,
            completed_at=utcnow(),
        )
        self.session.add(evaluation)
        self.session.flush()
        inputs = {r.criterion_code: r for r in data.results}
        criteria = {c.code: c for c in version.criteria}
        for scored in calculation.results:
            result = CriterionResult(
                evaluation_id=evaluation.id,
                criterion_id=criteria[scored.code].id,
                answer=str(scored.answer),
                raw_score=scored.raw_score,
                weighted_score=scored.weighted_score,
                is_na=scored.is_na,
                explanation=inputs[scored.code].explanation,
            )
            self.session.add(result)
            self.session.flush()
            for evidence in inputs[scored.code].evidence:
                self.session.add(Evidence(criterion_result_id=result.id, **evidence.model_dump()))
        self.session.flush()
        return evaluation

    def current_answers(self, evaluation: Evaluation):
        # Parse decimal answers through the same DTO as creation; never through float.
        from pydantic import TypeAdapter

        from app.schemas.checklists import Answer

        adapter = TypeAdapter(Answer)
        answers = {
            result.criterion_id: adapter.validate_python(result.answer)
            for result in evaluation.results
        }
        decisions = self.session.execute(
            select(Appeal.criterion_result_id, AppealDecision.revised_answer)
            .join(AppealDecision, AppealDecision.appeal_id == Appeal.id)
            .where(Appeal.evaluation_id == evaluation.id)
            .order_by(AppealDecision.id)
        )
        result_to_criterion = {r.id: r.criterion_id for r in evaluation.results}
        for result_id, answer in decisions:
            answers[result_to_criterion[result_id]] = adapter.validate_python(answer)
        return answers

    def detail(self, evaluation: Evaluation) -> EvaluationDetail:
        version = require(self.session, ChecklistVersion, evaluation.checklist_version_id)
        current = self.current_answers(evaluation)
        configs = [CriterionConfig.model_validate(c) for c in version.criteria]
        calculation = self.calculate(configs, [(c.code, current[c.id]) for c in version.criteria])
        by_code = {r.code: r for r in calculation.results}
        criteria = {c.id: c for c in version.criteria}
        results = []
        for result in evaluation.results:
            code = criteria[result.criterion_id].code
            scored = by_code[code]
            fields = {
                field: getattr(result, field)
                for field in (
                    "id",
                    "evaluation_id",
                    "criterion_id",
                    "answer",
                    "raw_score",
                    "weighted_score",
                    "is_na",
                    "explanation",
                    "created_at",
                    "evidence",
                )
            }
            results.append(
                CriterionResultRead(
                    **fields,
                    criterion_code=code,
                    current_answer=scored.answer,
                    current_raw_score=scored.raw_score,
                    current_weighted_score=scored.weighted_score,
                    current_is_na=scored.is_na,
                )
            )
        fields = {
            field: getattr(evaluation, field)
            for field in EvaluationDetail.model_fields
            if field not in {"results", "appeal_ids"}
        }
        appeal_ids = list(
            self.session.scalars(
                select(Appeal.id).where(Appeal.evaluation_id == evaluation.id).order_by(Appeal.id)
            )
        )
        return EvaluationDetail(**fields, results=results, appeal_ids=appeal_ids)

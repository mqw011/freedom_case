from app.models import Evaluation
from app.schemas.evaluations import EvaluationSubmission
from app.services.ai_contract import StructuredEvaluation
from app.services.evaluation_service import EvaluationService


def test_future_adapter_can_use_shared_pipeline(app, evaluation_payload):
    structured = StructuredEvaluation.model_validate({"results": evaluation_payload["results"]})
    schema = StructuredEvaluation.model_json_schema()
    assert schema["properties"]["results"]["items"]["$ref"].endswith("StructuredCriterionResult")
    data = EvaluationSubmission(
        conversation_id=evaluation_payload["conversation_id"],
        checklist_version_id=evaluation_payload["checklist_version_id"],
        source="ai",
        results=structured.results,
    )
    with app.state.session_factory() as session, session.begin():
        evaluation = EvaluationService(session).create(data)
        assert evaluation.source == "ai"
        assert str(evaluation.initial_score) == "81.88"
    with app.state.session_factory() as session:
        assert session.get(Evaluation, evaluation.id).source == "ai"

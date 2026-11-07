import copy
import json

import pytest

from app.ai.providers.base import Generation
from app.core.config import Settings
from app.schemas.checklists import VersionRead
from app.schemas.datasets import ConversationDetail
from app.services.ai_contract import EvaluationContext


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def ai_settings():
    return Settings(
        _env_file=None,
        llm_retry_delay=0,
        llm_context_length=32768,
        ai_poll_seconds=0.01,
        ai_retry_delay=0,
    )


@pytest.fixture
def context(client, imported):
    return EvaluationContext(
        conversation=ConversationDetail.model_validate(
            client.get(f"/api/conversations/{imported[0]['id']}").json()
        ),
        checklist_version=VersionRead.model_validate(
            client.get("/api/checklists/1/versions").json()[0]
        ),
    )


def grounded_result(context):
    first, last = context.conversation.messages[0], context.conversation.messages[-1]
    operator = next(m for m in context.conversation.messages if m.speaker == "operator")
    answers = {
        "01": "yes",
        "02": "yes",
        "03": "na",
        "04": "15",
        "05": "yes",
        "06": "7",
        "07": "no",
        "08": "no",
    }
    results = []
    for criterion in context.checklist_version.criteria:
        answer = answers.get(criterion.code, "yes")
        evidence = (
            {
                "evidence_type": "quote",
                "message_id": operator.id,
                "excerpt": operator.text,
                "explanation": "Observed action",
            }
            if answer not in {"na", "no"}
            else {
                "evidence_type": "absence",
                "message_id": first.id,
                "end_message_id": last.id,
                "explanation": "Checked the whole transcript for this condition",
            }
        )
        results.append(
            {
                "criterion_code": criterion.code,
                "answer": answer,
                "explanation": "Assessment based on the supplied transcript",
                "evidence": [evidence],
            }
        )
    return {"results": results}


class FakeProvider:
    """Test-only deterministic transport. Never imported by production code."""

    def __init__(self, result, *, error=None, semantic_reject=False):
        self.result = result
        self.error = error
        self.semantic_reject = semantic_reject
        self.calls = []

    async def generate_structured(self, messages, response_schema):
        self.calls.append(messages)
        if self.error:
            raise self.error
        if "decisions" in response_schema.get("properties", {}):
            proposed = json.loads(messages[-1]["content"])["untrusted_proposed_assessment"]
            data = {
                "decisions": [
                    {
                        "criterion_code": r["criterion_code"],
                        "supported": not self.semantic_reject,
                        "issue": "contradiction" if self.semantic_reject else "none",
                        "needs_human_review": False,
                    }
                    for r in proposed["results"]
                ]
            }
        else:
            data = copy.deepcopy(self.result)
        return Generation(data, 5, 100, 100)

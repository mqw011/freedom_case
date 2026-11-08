from decimal import Decimal

import pytest

from app.ai.benchmark.__main__ import configuration, summarize
from app.ai.benchmark.cases import CASES, make_context
from app.core.config import Settings
from app.services.scoring_engine import score


def test_benchmark_metadata_reproduces_settings_without_secrets():
    settings = Settings(
        llm_think=True,
        llm_temperature=0.6,
        llm_max_output_tokens=8192,
        llm_api_key="private-provider-token",
        dataset_api_url="https://example.com/dataset?sig=private-signature",
    )
    public = configuration(settings)
    assert public["inference_settings"]["llm_think"] is True
    assert public["inference_settings"]["llm_max_output_tokens"] == 8192
    assert public["prompt_version"]
    assert "private-" not in str(public)
    assert "llm_base_url" not in public["inference_settings"]


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_reference_case_is_complete_and_valid(case):
    name, language, messages, expected = case
    context = make_context(name, language, messages)
    result = score(
        context.checklist_version.criteria,
        [(c, Decimal(v) if v.isdigit() else v) for c, v in expected.items()],
    )
    assert result.final_score is not None and len(result.results) == 8
    assert context.conversation.language == language


def test_metrics_do_not_count_failures_as_correct():
    result = summarize(
        [
            {
                "status": "failed",
                "language": "KZ",
                "latency_seconds": 2,
                "metrics": {
                    "assessment_requests": 1,
                    "successful_json": 1,
                    "requests": 1,
                    "schema_valid": 1,
                    "complete_results": 1,
                    "grounded_results": 0,
                },
            }
        ]
    )
    assert result["evidence_validity_rate"] == 0
    assert result["criterion_agreement"] is None
    assert result["failures_by_language"] == {"KZ": 1}

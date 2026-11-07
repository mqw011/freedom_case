import json
from decimal import Decimal

from pydantic import ValidationError

from app.ai.exceptions import OutputError
from app.services.ai_contract import StructuredEvaluation


def parse_json(content: str) -> dict:
    def reject_constant(_):
        raise ValueError("Nonfinite JSON number")

    def unique_keys(pairs):
        output = {}
        for key, value in pairs:
            if key in output:
                raise ValueError("Duplicate JSON key")
            output[key] = value
        return output

    cleaned = content.strip()
    if cleaned.startswith("```json\n") and cleaned.endswith("\n```"):
        cleaned = cleaned[8:-4]
    try:
        result = json.loads(
            cleaned,
            parse_float=Decimal,
            parse_constant=reject_constant,
            object_pairs_hook=unique_keys,
        )
        if not isinstance(result, dict):
            raise ValueError("Expected object")
        return result
    except (ValueError, TypeError, RecursionError):
        raise OutputError("invalid_json") from None


def parse_evaluation(data: dict) -> StructuredEvaluation:
    try:
        return StructuredEvaluation.model_validate(data)
    except ValidationError:
        raise OutputError("invalid_schema") from None

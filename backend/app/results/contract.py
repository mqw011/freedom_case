"""PDF format 1.0, Decimal JSON and validation; never print rejected source values."""

import json
import os
import tempfile
from decimal import Decimal
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator

from app.seed.default_checklist import default_checklist
from app.services.scoring_engine import score

IDS = dict(
    zip(
        (f"{i:02}" for i in range(1, 9)),
        (
            "contact",
            "discovery",
            "identification",
            "consultation",
            "empathy",
            "dialogue",
            "closure",
            "critical",
        ),
        strict=True,
    )
)
COUNTS = {"dev": 65, "prod": 10}


class ResultsError(Exception):
    def __init__(self, code, location=None):
        self.code = code
        self.location = location
        super().__init__(code)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ResultsError("duplicate_json_key")
        result[key] = value
    return result


def _constant(_):
    raise ResultsError("nonfinite_number")


def loads(text):
    try:
        return json.loads(
            text, parse_float=Decimal, parse_constant=_constant, object_pairs_hook=_pairs
        )
    except (ValueError, UnicodeError, RecursionError):
        raise ResultsError("invalid_json") from None


def read_document(path):
    if Path(path).stat().st_size > 20 * 1024 * 1024:
        raise ResultsError("results_file_too_large")
    return loads(Path(path).read_text(encoding="utf-8"))


def dumps(value):
    """Emit Decimal as a JSON number, never as a string or through binary float."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ResultsError("nonfinite_number")
        return format(value, "f")
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise ResultsError("invalid_json_key")
        return (
            "{"
            + ",".join(json.dumps(k, ensure_ascii=False) + ":" + dumps(v) for k, v in value.items())
            + "}"
        )
    if isinstance(value, list):
        return "[" + ",".join(dumps(v) for v in value) + "]"
    if value is None or isinstance(value, (str, bool, int)):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    raise ResultsError("unsupported_json_type")


def write_document(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Validate the serialized bytes too; atomically replace, never append/merge old results.
    content = dumps(document) + "\n"
    validate(loads(content))
    descriptor, temporary = tempfile.mkstemp(prefix=".results-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def to_answer(value):
    if value is None:
        return "na"
    if type(value) is bool:
        return "yes" if value else "no"
    return Decimal(value)


def validate(document, *, kind=None, expected_turns=None, require_complete=False):
    schema = loads(files("app.results").joinpath("schema-1.0.json").read_text())
    validator = Draft202012Validator(schema)
    error = next(validator.iter_errors(document), None)
    if error:
        # jsonschema's message/repr can contain a private rationale: return only path/code.
        raise ResultsError("schema_invalid", list(error.absolute_path))
    if not document["team_name"].strip() or not document["model"]["name"].strip():
        raise ResultsError("metadata_empty")
    rows = document["results"]
    identifiers = [r["conversation_id"] for r in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ResultsError("duplicate_conversation_id")
    if kind and len(rows) != COUNTS[kind]:
        raise ResultsError("dataset_count_mismatch")
    if expected_turns is not None and set(identifiers) != set(expected_turns):
        raise ResultsError("dataset_ids_mismatch")
    errors = 0
    configs = default_checklist().version.criteria
    for index, row in enumerate(rows):
        if row["status"] == "error":
            if not row["error"].strip():
                raise ResultsError("empty_error", index)
            errors += 1
            continue
        criteria = {c["criterion_id"]: c for c in row["criteria"]}
        if set(criteria) != set(IDS.values()):
            raise ResultsError("criterion_ids_mismatch", index)
        for criterion in criteria.values():
            if not criterion["rationale"].strip():
                raise ResultsError("empty_rationale", index)
            if expected_turns is not None and any(
                turn > expected_turns[row["conversation_id"]]
                for turn in criterion["evidence_turns"]
            ):
                raise ResultsError("evidence_turn_out_of_bounds", index)
        calculated = score(
            configs, [(code, to_answer(criteria[name]["value"])) for code, name in IDS.items()]
        )
        if Decimal(row["score"]["final_score"]) != calculated.final_score:
            raise ResultsError("final_score_mismatch", index)
        if row["score"]["critical_flag"] is not calculated.critical_violation:
            raise ResultsError("critical_flag_mismatch", index)
    if require_complete and errors:
        raise ResultsError("incomplete_evaluations")
    return {
        "records": len(rows),
        "ok": len(rows) - errors,
        "error": errors,
        "schema_version": "1.0",
    }

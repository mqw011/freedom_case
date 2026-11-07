from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.checklists import CriterionConfig
from app.seed.default_checklist import default_checklist
from app.services.scoring_engine import ScoringError, score


@pytest.fixture
def criteria():
    return default_checklist().version.criteria


def best(criteria):
    return [
        (
            c.code,
            c.max_score
            if c.criterion_type == "scale"
            else "no"
            if c.criterion_type == "flag"
            else "yes",
        )
        for c in criteria
    ]


def with_answer(criteria, code, answer):
    return [(key, answer if key == code else value) for key, value in best(criteria)]


def test_all_yes_is_100(criteria):
    result = score(criteria, best(criteria))
    assert result.final_score == Decimal("100.00")
    assert result.applicable_weight == 100


def test_all_no_is_zero(criteria):
    answers = [(c.code, Decimal(0) if c.criterion_type == "scale" else "no") for c in criteria]
    assert score(criteria, answers).final_score == Decimal("0.00")


@pytest.mark.parametrize(
    "code,raw,weighted",
    [
        ("04", "0", "0"),
        ("04", "5", "5"),
        ("04", "10", "10"),
        ("04", "15", "15"),
        ("04", "20", "20"),
        ("06", "0", "0"),
        ("06", "4", "6"),
        ("06", "7", "10.5"),
        ("06", "10", "15"),
    ],
)
def test_discrete_scales(criteria, code, raw, weighted):
    result = score(criteria, with_answer(criteria, code, Decimal(raw)))
    assert next(r.weighted_score for r in result.results if r.code == code) == Decimal(weighted)


@pytest.mark.parametrize("code,weight", [("02", 15), ("03", 20), ("04", 20), ("07", 5)])
def test_na_redistributes_weight(criteria, code, weight):
    result = score(criteria, with_answer(criteria, code, "na"))
    assert result.applicable_weight == 100 - weight
    assert result.final_score == 100
    criterion = next(r for r in result.results if r.code == code)
    assert criterion.is_na and criterion.weighted_score is None and criterion.raw_score is None


def test_multiple_na(criteria):
    answers = [(k, "na" if k in {"02", "03", "04", "07"} else v) for k, v in best(criteria)]
    result = score(criteria, answers)
    assert result.applicable_weight == 40
    assert result.final_score == 100


@pytest.mark.parametrize("code", ["01", "05", "06", "08"])
def test_forbidden_na(criteria, code):
    with pytest.raises(ScoringError, match="does not allow N/A"):
        score(criteria, with_answer(criteria, code, "na"))


@pytest.mark.parametrize(
    "code,value",
    [
        ("04", Decimal(12)),
        ("04", Decimal(17)),
        ("06", Decimal(8)),
        ("01", Decimal(1)),
        ("04", "yes"),
        ("04", Decimal(-1)),
    ],
)
def test_invalid_answer(criteria, code, value):
    with pytest.raises(ScoringError):
        score(criteria, with_answer(criteria, code, value))


def test_reference_example_and_half_up(criteria):
    answers = {
        "01": "yes",
        "02": "yes",
        "03": "na",
        "04": Decimal(15),
        "05": "yes",
        "06": Decimal(7),
        "07": "no",
        "08": "no",
    }
    result = score(criteria, list(answers.items()))
    assert result.earned_total == Decimal("65.5")
    assert result.applicable_weight == 80
    assert result.final_score == Decimal("81.88")


def test_flag_does_not_zero_score(criteria):
    result = score(criteria, with_answer(criteria, "08", "yes"))
    assert result.final_score == 100
    assert result.critical_violation


def custom(**overrides):
    return CriterionConfig.model_validate(
        {
            "code": "custom",
            "title": "Custom",
            "description": "Custom criterion",
            "section": "Additional section",
            "criterion_type": "scale",
            "weight": "100",
            "allowed_values": [0, 1, 3],
            "max_score": 3,
            "allow_na": True,
            "na_condition": "Not applicable",
            "display_order": 1,
            **overrides,
        }
    )


def test_no_applicable_criteria_returns_null():
    result = score([custom()], [("custom", "na")])
    assert result.final_score is None
    assert result.applicable_weight == 0


def test_flag_only_returns_null(criteria):
    result = score([criteria[-1]], [("08", "yes")])
    assert result.final_score is None and result.critical_violation


def test_custom_weight_and_fraction():
    result = score([custom(weight="27.5")], [("custom", Decimal(1))])
    assert result.final_score == Decimal("33.33")
    assert result.results[0].weighted_score != Decimal("9.17")  # no intermediate rounding


def test_adding_new_criterion(criteria):
    more = criteria + [custom(weight=25, display_order=9)]
    result = score(more, best(criteria) + [("custom", Decimal(0))])
    assert result.final_score == 80


def test_changed_scale_without_code_rules():
    criterion = custom(allowed_values=[0, 2, 8], max_score=8)
    assert score([criterion], [("custom", Decimal(2))]).final_score == 25


@pytest.mark.parametrize("mode", ["missing", "duplicate", "unknown"])
def test_results_must_be_complete(criteria, mode):
    answers = best(criteria)
    if mode == "missing":
        answers.pop()
    elif mode == "duplicate":
        answers.append(answers[0])
    else:
        answers.append(("unknown", "yes"))
    with pytest.raises(ScoringError):
        score(criteria, answers)


@pytest.mark.parametrize(
    "change",
    [
        {"weight": -1},
        {"allowed_values": [0, 1, 1, 3]},
        {"max_score": 4},
        {"max_score": 0},
        {"allowed_values": [1, 3]},
        {"na_condition": None},
        {"allow_na": False},
        {"weight": "NaN"},
        {"weight": "Infinity"},
        {"scale_labels": {"2": "Not an allowed step"}},
    ],
)
def test_invalid_configuration(change):
    with pytest.raises(ValidationError):
        custom(**change)

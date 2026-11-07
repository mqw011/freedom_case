from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, StrictBool, model_validator

from app.schemas.common import NonEmpty, PositiveId, Schema

Score = Annotated[Decimal, Field(ge=0, max_digits=16, decimal_places=6, allow_inf_nan=False)]
Answer = Literal["yes", "no", "na"] | Score


class CriterionConfig(Schema):
    code: NonEmpty = Field(max_length=40)
    title: NonEmpty = Field(max_length=300)
    description: NonEmpty
    section: NonEmpty = Field(max_length=300)
    criterion_type: Literal["binary", "scale", "flag"]
    weight: Score = Field(le=100)
    allowed_values: list[Score] = Field(min_length=2, max_length=100)
    max_score: Score = Field(gt=0)
    allow_na: StrictBool = False
    na_condition: NonEmpty | None = None
    scale_labels: dict[str, NonEmpty] = Field(default_factory=dict)
    display_order: int = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def consistency(self):
        if len(set(self.allowed_values)) != len(self.allowed_values):
            raise ValueError("Scale values must be unique")
        if min(self.allowed_values) != 0 or max(self.allowed_values) != self.max_score:
            raise ValueError("Scale must start at zero and end at max_score")
        if self.criterion_type in {"binary", "flag"}:
            if set(self.allowed_values) != {Decimal(0), Decimal(1)} or self.max_score != 1:
                raise ValueError("Binary/flag scale must be [0, 1], max_score=1")
        if self.criterion_type == "flag" and (self.weight != 0 or self.allow_na):
            raise ValueError("Flags must have zero weight and cannot allow N/A")
        if self.criterion_type != "flag" and self.weight <= 0:
            raise ValueError("Scored criteria require a positive weight")
        if self.allow_na != (self.na_condition is not None):
            raise ValueError("N/A requires a condition; non-N/A criteria must omit it")
        for key in self.scale_labels:
            try:
                valid = Decimal(key) in self.allowed_values
            except ArithmeticError:
                valid = False
            if not valid:
                raise ValueError("Scale labels must reference allowed values")
        return self


class VersionCreate(Schema):
    criteria: list[CriterionConfig] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_criteria(self):
        if len({c.code for c in self.criteria}) != len(self.criteria):
            raise ValueError("Criterion codes must be unique")
        if len({c.display_order for c in self.criteria}) != len(self.criteria):
            raise ValueError("Criterion display_order must be unique")
        return self


class ChecklistCreate(Schema):
    name: NonEmpty = Field(max_length=300)
    description: NonEmpty
    version: VersionCreate


class ActivateRequest(Schema):
    version_id: PositiveId


class CriterionRead(CriterionConfig):
    id: int
    checklist_version_id: int


class VersionRead(Schema):
    id: int
    checklist_id: int
    version_number: int
    status: str
    created_at: datetime
    criteria: list[CriterionRead]


class ChecklistRead(Schema):
    id: int
    name: str
    description: str
    active_version_id: int | None
    created_at: datetime
    updated_at: datetime

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]
GroupId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]
PositiveId = Annotated[int, Field(gt=0, strict=True)]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class Page[T](Schema):
    items: list[T]
    total: int
    offset: int
    limit: int


class ErrorDetail(Schema):
    code: str
    message: str
    details: list[dict] | None = None


class ErrorResponse(Schema):
    error: ErrorDetail

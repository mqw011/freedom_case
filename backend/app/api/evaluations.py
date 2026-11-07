from typing import Annotated, Literal

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.dependencies import DB, Limit, Offset
from app.models import Evaluation
from app.schemas.common import Page
from app.schemas.evaluations import EvaluationCreate, EvaluationDetail, EvaluationRead
from app.services.common import page, require
from app.services.evaluation_service import EvaluationService

router = APIRouter(prefix="/evaluations", tags=["Evaluations"])


@router.post("", response_model=EvaluationDetail, status_code=201)
def create_evaluation(data: EvaluationCreate, db: DB):
    service = EvaluationService(db)
    return service.detail(service.create(data))


@router.get("", response_model=Page[EvaluationRead])
def evaluations(
    db: DB,
    offset: Offset = 0,
    limit: Limit = 50,
    conversation_id: Annotated[int | None, Query(gt=0)] = None,
    source: Literal["manual", "test", "ai"] | None = None,
):
    statement = select(Evaluation)
    if conversation_id:
        statement = statement.where(Evaluation.conversation_id == conversation_id)
    if source:
        statement = statement.where(Evaluation.source == source)
    return page(db, statement.order_by(Evaluation.id), offset, limit)


@router.get("/{evaluation_id}", response_model=EvaluationDetail)
def evaluation(evaluation_id: int, db: DB):
    return EvaluationService(db).detail(require(db, Evaluation, evaluation_id))

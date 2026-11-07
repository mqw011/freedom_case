from typing import Literal

from fastapi import APIRouter
from sqlalchemy import select

from app.api.dependencies import DB, Limit, Offset
from app.models import Appeal
from app.schemas.appeals import AppealCreate, AppealRead, DecisionCreate
from app.schemas.common import Page
from app.services.appeal_service import AppealService
from app.services.common import page, require

router = APIRouter(tags=["Appeals"])


@router.post("/evaluations/{evaluation_id}/appeals", response_model=AppealRead, status_code=201)
def create_appeal(evaluation_id: int, data: AppealCreate, db: DB):
    return AppealService(db).create(evaluation_id, data)


@router.get("/appeals", response_model=Page[AppealRead])
def appeals(
    db: DB,
    offset: Offset = 0,
    limit: Limit = 50,
    status: Literal["pending", "upheld", "revised"] | None = None,
):
    statement = select(Appeal)
    if status:
        statement = statement.where(Appeal.status == status)
    return page(db, statement.order_by(Appeal.id), offset, limit)


@router.get("/appeals/{appeal_id}", response_model=AppealRead)
def appeal(appeal_id: int, db: DB):
    return require(db, Appeal, appeal_id)


@router.post("/appeals/{appeal_id}/decision", response_model=AppealRead)
def decide(appeal_id: int, data: DecisionCreate, db: DB):
    return AppealService(db).decide(appeal_id, data)

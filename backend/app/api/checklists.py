from fastapi import APIRouter
from sqlalchemy import select

from app.api.dependencies import DB, Limit, Offset
from app.models import Checklist, ChecklistVersion
from app.schemas.checklists import (
    ActivateRequest,
    ChecklistCreate,
    ChecklistRead,
    VersionCreate,
    VersionRead,
)
from app.schemas.common import Page
from app.services.checklist_service import ChecklistService
from app.services.common import page, require

router = APIRouter(prefix="/checklists", tags=["Checklists"])


@router.get("", response_model=Page[ChecklistRead])
def checklists(db: DB, offset: Offset = 0, limit: Limit = 50):
    return page(db, select(Checklist).order_by(Checklist.id), offset, limit)


@router.post("", response_model=ChecklistRead, status_code=201)
def create_checklist(data: ChecklistCreate, db: DB):
    return ChecklistService(db).create(data)


@router.get("/{checklist_id}", response_model=ChecklistRead)
def checklist(checklist_id: int, db: DB):
    return require(db, Checklist, checklist_id)


@router.get("/{checklist_id}/versions", response_model=list[VersionRead])
def versions(checklist_id: int, db: DB):
    require(db, Checklist, checklist_id)
    return db.scalars(
        select(ChecklistVersion)
        .where(ChecklistVersion.checklist_id == checklist_id)
        .order_by(ChecklistVersion.version_number)
    ).all()


@router.post("/{checklist_id}/versions", response_model=VersionRead, status_code=201)
def new_version(checklist_id: int, data: VersionCreate, db: DB):
    return ChecklistService(db).new_version(checklist_id, data)


@router.post("/{checklist_id}/activate", response_model=ChecklistRead)
def activate(checklist_id: int, data: ActivateRequest, db: DB):
    return ChecklistService(db).activate(checklist_id, data.version_id)

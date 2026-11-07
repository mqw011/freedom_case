from typing import Literal

from fastapi import APIRouter
from sqlalchemy import text

from app.api.dependencies import DB
from app.schemas.common import Schema

router = APIRouter(tags=["Health"])


class HealthRead(Schema):
    status: Literal["ok"]
    database: Literal["ok"]


@router.get("/health", response_model=HealthRead)
def health(db: DB):
    db.execute(text("SELECT 1"))
    # Verify the application schema is migrated as well as the connection being live.
    db.execute(text("SELECT version_num FROM alembic_version"))
    db.execute(text("SELECT id FROM checklists LIMIT 1"))
    return HealthRead(status="ok", database="ok")

from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import get_session

DB = Annotated[Session, Depends(get_session, scope="function")]
Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]


def get_config(request: Request) -> Settings:
    return request.app.state.settings


Config = Annotated[Settings, Depends(get_config)]

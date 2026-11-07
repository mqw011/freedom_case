from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import DomainError


def require(session: Session, model, identifier: int):
    obj = session.get(model, identifier)
    if obj is None:
        raise DomainError(404, "not_found", f"{model.__name__} not found")
    return obj


def page(session: Session, statement, offset: int, limit: int):
    total = session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    items = session.scalars(statement.offset(offset).limit(limit)).all()
    return {"items": items, "total": total, "offset": offset, "limit": limit}

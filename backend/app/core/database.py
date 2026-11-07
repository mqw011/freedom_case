from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from fastapi import Request
from sqlalchemy import DateTime, Engine, String, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class ExactDecimal(TypeDecorator):
    """Portable decimal text storage: SQLite NUMERIC would round-trip through float."""

    impl = String(100)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else str(Decimal(value))

    def process_result_value(self, value, dialect):
        return None if value is None else Decimal(value)


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("Timezone-aware datetimes are required")
            return value.astimezone(UTC)
        return None

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


def utcnow() -> datetime:
    return datetime.now(UTC)


def build_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    options = {}
    if url.get_backend_name() == "sqlite":
        if url.database and url.database != ":memory:":
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        options["connect_args"] = {"check_same_thread": False, "timeout": 15}
    engine = create_engine(url, **options)
    if url.get_backend_name() == "sqlite":

        @event.listens_for(engine, "connect")
        def sqlite_connect(connection, _):
            # Explicit BEGIN also makes DDL/savepoints transactional on Python 3.12+.
            connection.isolation_level = None
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=15000")

        @event.listens_for(engine, "begin")
        def sqlite_begin(connection):
            connection.exec_driver_sql("BEGIN")

    return engine


def get_session(request: Request) -> Generator[Session]:
    with request.app.state.session_factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

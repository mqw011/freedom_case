import json
import logging
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException


class DomainError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message
        super().__init__(message)


class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "event": record.getMessage(),
            },
            ensure_ascii=False,
        )


def configure_logging(level: str):
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger = logging.getLogger("cqa")
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False


def install_handlers(app: FastAPI):
    def response(status, code, message, details=None):
        body = {"error": {"code": code, "message": message}}
        if details is not None:
            body["error"]["details"] = details
        return JSONResponse(status_code=status, content=body)

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        return response(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Never echo input, request bodies, tokens or Pydantic ctx exceptions.
        details = [
            {"loc": list(e["loc"]), "type": e["type"], "message": e["msg"]} for e in exc.errors()
        ]
        return response(422, "validation_error", "Request validation failed", details)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return response(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(IntegrityError)
    @app.exception_handler(StaleDataError)
    async def conflict(request: Request, exc: Exception):
        return response(409, "conflict", "Conflicting or concurrent update; refresh and retry")

    @app.exception_handler(OperationalError)
    async def unavailable(request: Request, exc: Exception):
        logging.getLogger("cqa").error("database_unavailable")
        return response(
            503, "database_unavailable", "Database unavailable; check migrations or retry"
        )

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        logging.getLogger("cqa").error("unexpected_error type=%s", type(exc).__name__)
        return response(500, "internal_error", "Internal server error")

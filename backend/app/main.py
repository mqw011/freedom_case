import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker

from app.api import ai, appeals, checklists, conversations, datasets, evaluations, health
from app.core.config import Settings, get_settings
from app.core.database import build_engine
from app.core.exceptions import configure_logging, install_handlers
from app.schemas.common import ErrorResponse


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = build_engine(settings.database_url)
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        worker = task = None
        if settings.ai_auto_start_worker and settings.ai_job_enabled:
            from app.ai.worker import Worker

            worker = Worker(app.state.session_factory, settings)
            task = asyncio.create_task(worker.run())
        try:
            yield
        finally:
            if worker:
                worker.stop.set()
                await task
            engine.dispose()

    app = FastAPI(
        title="Freedom Broker CQA",
        version="0.2.0",
        lifespan=lifespan,
        description="CQA: versioned evaluations, appeals and durable local-first AI jobs.",
        responses={code: {"model": ErrorResponse} for code in (400, 404, 409, 422, 502, 503)},
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    install_handlers(app)

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        route = request.scope.get("route")
        logging.getLogger("cqa.http").info(
            "request method=%s route=%s status=%d duration_ms=%d",
            request.method,
            getattr(route, "path", "unmatched"),
            response.status_code,
            int((time.monotonic() - start) * 1000),
        )
        return response

    for router in (
        health.router,
        ai.router,
        datasets.router,
        conversations.router,
        checklists.router,
        evaluations.router,
        appeals.router,
    ):
        app.include_router(router, prefix="/api")
    return app


app = create_app()

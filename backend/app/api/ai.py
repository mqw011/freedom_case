from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.ai.exceptions import AIError
from app.ai.jobs import JobService
from app.ai.providers import make_provider
from app.api.dependencies import DB, Config, Limit, Offset
from app.core.database import utcnow
from app.models.ai import AIBatch, AIJob, AIJobAttempt, AIWorkerLease
from app.schemas.ai import (
    AIBatchCreate,
    AIBatchRead,
    AIHealth,
    AIJobAttemptRead,
    AIJobCreate,
    AIJobRead,
    JobStatus,
    RetryBatchRead,
)
from app.schemas.common import Page
from app.services.common import page, require

router = APIRouter(prefix="/ai", tags=["AI jobs"])


@router.post("/evaluations", response_model=AIJobRead, status_code=202)
def create_job(data: AIJobCreate, db: DB, config: Config):
    return JobService(db, config).create(data)


@router.post("/batches", response_model=AIBatchRead, status_code=202)
def create_batch(data: AIBatchCreate, db: DB, config: Config):
    service = JobService(db, config)
    return service.batch_detail(service.create_batch(data))


@router.get("/jobs", response_model=Page[AIJobRead])
def jobs(
    db: DB,
    offset: Offset = 0,
    limit: Limit = 50,
    status: JobStatus | None = None,
    batch_id: Annotated[int | None, Query(gt=0)] = None,
    conversation_id: Annotated[int | None, Query(gt=0)] = None,
):
    statement = select(AIJob)
    if status:
        statement = statement.where(AIJob.status == status)
    if batch_id:
        statement = statement.where(AIJob.batch_id == batch_id)
    if conversation_id:
        statement = statement.where(AIJob.conversation_id == conversation_id)
    return page(db, statement.order_by(AIJob.id), offset, limit)


@router.get("/jobs/{job_id}", response_model=AIJobRead)
def job(job_id: int, db: DB):
    return require(db, AIJob, job_id)


@router.get("/jobs/{job_id}/attempts", response_model=Page[AIJobAttemptRead])
def attempts(job_id: int, db: DB, offset: Offset = 0, limit: Limit = 50):
    require(db, AIJob, job_id)
    return page(
        db,
        select(AIJobAttempt)
        .where(AIJobAttempt.job_id == job_id)
        .order_by(AIJobAttempt.attempt_number),
        offset,
        limit,
    )


@router.post("/jobs/{job_id}/retry", response_model=AIJobRead, status_code=202)
def retry(job_id: int, db: DB, config: Config):
    return JobService(db, config).retry(job_id)


@router.post("/jobs/{job_id}/cancel", response_model=AIJobRead)
def cancel(job_id: int, db: DB, config: Config):
    return JobService(db, config).cancel(job_id)


@router.get("/batches", response_model=Page[AIBatchRead])
def batches(db: DB, config: Config, offset: Offset = 0, limit: Limit = 50):
    result = page(db, select(AIBatch).order_by(AIBatch.id), offset, limit)
    result["items"] = [JobService(db, config).batch_detail(b) for b in result["items"]]
    return result


@router.get("/batches/{batch_id}", response_model=AIBatchRead)
def batch(batch_id: int, db: DB, config: Config):
    return JobService(db, config).batch_detail(require(db, AIBatch, batch_id))


@router.get("/batches/{batch_id}/jobs", response_model=Page[AIJobRead])
def batch_jobs(batch_id: int, db: DB, offset: Offset = 0, limit: Limit = 50):
    require(db, AIBatch, batch_id)
    return page(
        db, select(AIJob).where(AIJob.batch_id == batch_id).order_by(AIJob.id), offset, limit
    )


@router.post("/batches/{batch_id}/retry-failed", response_model=RetryBatchRead, status_code=202)
def retry_batch(batch_id: int, db: DB, config: Config):
    require(db, AIBatch, batch_id)
    ids = list(
        db.scalars(select(AIJob.id).where(AIJob.batch_id == batch_id, AIJob.status == "failed"))
    )
    service = JobService(db, config)
    for job_id in ids:
        service.retry(job_id)
    return RetryBatchRead(batch_id=batch_id, retried=len(ids))


@router.get("/health", response_model=AIHealth)
async def health(request: Request, config: Config):
    # Close the read transaction before contacting the provider.
    with request.app.state.session_factory() as session:
        lease = session.get(AIWorkerLease, 1)
        worker = {
            "available": bool(
                lease and lease.owner and lease.expires_at and lease.expires_at > utcnow()
            ),
            "heartbeat_at": lease.heartbeat_at if lease else None,
            "lease_expires_at": lease.expires_at if lease else None,
            "concurrency": lease.concurrency if lease else config.llm_max_concurrency,
        }
    try:
        provider = await make_provider(config).health()
    except AIError as exc:
        provider = {"available": False, "model": config.llm_model, "error_code": exc.code}
    return AIHealth(enabled=config.ai_job_enabled, provider=provider, worker=worker)

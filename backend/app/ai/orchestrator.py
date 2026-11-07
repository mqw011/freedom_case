import asyncio
import time
from dataclasses import asdict
from datetime import timedelta

from sqlalchemy import update

from app.ai.evaluator import LLMEvaluator
from app.ai.exceptions import AIError
from app.ai.jobs import PINNED_SETTINGS
from app.ai.prompt_engine import PROMPT_VERSION
from app.ai.providers import make_provider
from app.core.database import utcnow
from app.models import ChecklistVersion, Conversation
from app.models.ai import AIJob, AIJobAttempt
from app.schemas.checklists import VersionRead
from app.schemas.datasets import ConversationDetail
from app.schemas.evaluations import EvaluationSubmission
from app.services.ai_contract import EvaluationContext
from app.services.evaluation_service import EvaluationService


def load_context(factory, job_id):
    with factory() as session:
        job = session.get(AIJob, job_id)
        context = EvaluationContext(
            conversation=ConversationDetail.model_validate(
                session.get(Conversation, job.conversation_id)
            ),
            checklist_version=VersionRead.model_validate(
                session.get(ChecklistVersion, job.checklist_version_id)
            ),
        )
        return context, job.inference_config, job.provider, job.model


def lock_owned_job(session, job_id, owner, token):
    # The first statement is a write/CAS; no SQLite read-to-write transaction upgrade.
    now = utcnow()
    changed = session.scalar(
        update(AIJob)
        .where(
            AIJob.id == job_id,
            AIJob.status == "running",
            AIJob.owner == owner,
            AIJob.claim_token == token,
            AIJob.lease_expires_at > now,
        )
        .values(lease_expires_at=AIJob.lease_expires_at)
        .returning(AIJob.id)
    )
    return session.get(AIJob, changed) if changed else None


def finish_success(factory, job_id, owner, token, output, diagnostics):
    with factory() as session, session.begin():
        job = lock_owned_job(session, job_id, owner, token)
        if job is None:
            return None
        if job.cancel_requested:
            job.status = "cancelled"
        else:
            submission = EvaluationSubmission(
                conversation_id=job.conversation_id,
                checklist_version_id=job.checklist_version_id,
                source="ai",
                results=output.results,
            )
            evaluation = EvaluationService(session).create(submission)
            job.evaluation_id = evaluation.id
            job.status = "completed"
        job.completed_at = utcnow()
        job.diagnostics = diagnostics
        job.owner = job.claim_token = job.lease_expires_at = None
        session.execute(
            update(AIJobAttempt)
            .where(AIJobAttempt.job_id == job.id, AIJobAttempt.attempt_number == job.attempts)
            .values(status=job.status, finished_at=job.completed_at, diagnostics=diagnostics)
        )
        return job.evaluation_id


def finish_failure(factory, job_id, owner, token, error, diagnostics, settings):
    with factory() as session, session.begin():
        job = lock_owned_job(session, job_id, owner, token)
        if job is None:
            return
        now = utcnow()
        if job.cancel_requested:
            error = AIError("cancelled")
            job.status = "cancelled"
        elif error.retryable and job.attempts < job.max_attempts:
            job.status = "queued"
            job.next_attempt_at = now + timedelta(seconds=settings.ai_retry_delay)
        else:
            job.status = "failed"
        job.error_code = error.code
        job.safe_error_message = error.safe_message
        job.diagnostics = diagnostics
        job.completed_at = now if job.status in {"failed", "cancelled"} else None
        job.owner = job.claim_token = job.lease_expires_at = None
        session.execute(
            update(AIJobAttempt)
            .where(AIJobAttempt.job_id == job.id, AIJobAttempt.attempt_number == job.attempts)
            .values(
                status="cancelled" if job.cancel_requested else "failed",
                error_code=error.code,
                finished_at=now,
                diagnostics=diagnostics,
            )
        )


class AIOrchestrator:
    def __init__(self, factory, settings, *, provider_factory=make_provider):
        self.factory = factory
        self.settings = settings
        self.provider_factory = provider_factory

    async def process(self, job_id, owner, token):
        start = time.monotonic()
        evaluator = None
        diagnostics = {}
        try:
            context, config, provider, model = await asyncio.to_thread(
                load_context, self.factory, job_id
            )
            settings = self.settings.model_copy(
                update={k: v for k, v in config.items() if k in PINNED_SETTINGS}
                | {"llm_provider": provider, "llm_model": model}
            )
            evaluator = LLMEvaluator(self.provider_factory(settings), settings)
            output = await evaluator.evaluate(context)
            diagnostics = asdict(evaluator.metrics)
            diagnostics["prompt_version"] = PROMPT_VERSION
            diagnostics["needs_human_review"] = bool(evaluator.metrics.review_codes)
            return await asyncio.to_thread(
                finish_success, self.factory, job_id, owner, token, output, diagnostics
            )
        except asyncio.CancelledError:
            error = AIError("worker_stopped", retryable=True)
        except AIError as exc:
            error = exc
        except Exception as exc:
            diagnostics["exception_type"] = type(exc).__name__
            error = AIError("worker_error")
        if evaluator:
            diagnostics.update(asdict(evaluator.metrics))
        diagnostics["prompt_version"] = PROMPT_VERSION
        diagnostics["latency_ms"] = int((time.monotonic() - start) * 1000)
        await asyncio.to_thread(
            finish_failure, self.factory, job_id, owner, token, error, diagnostics, self.settings
        )
        return None

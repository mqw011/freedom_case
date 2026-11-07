import argparse
import asyncio
import logging
import signal
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

from app.ai.jobs import acquire_worker, claim_job, recover_expired
from app.ai.orchestrator import AIOrchestrator
from app.core.config import get_settings
from app.core.database import build_engine, utcnow
from app.core.exceptions import configure_logging
from app.models.ai import AIJob, AIWorkerLease

logger = logging.getLogger("cqa.worker")


class Worker:
    def __init__(self, factory, settings, *, orchestrator=None):
        self.factory = factory
        self.settings = settings
        self.owner = uuid4().hex
        self.stop = asyncio.Event()
        self.orchestrator = orchestrator or AIOrchestrator(factory, settings)

    def acquire(self):
        with self.factory() as session, session.begin():
            if not acquire_worker(session, self.owner, self.settings):
                return False
            recover_expired(session)
            return True

    def heartbeat(self):
        now = utcnow()
        expires = now + timedelta(seconds=self.settings.ai_lease_seconds)
        with self.factory() as session, session.begin():
            result = session.execute(
                update(AIWorkerLease)
                .where(
                    AIWorkerLease.id == 1,
                    AIWorkerLease.owner == self.owner,
                    AIWorkerLease.expires_at > now,
                )
                .values(heartbeat_at=now, expires_at=expires)
            )
            if result.rowcount != 1:
                return None
            session.execute(
                update(AIJob)
                .where(AIJob.owner == self.owner, AIJob.status == "running")
                .values(lease_expires_at=expires)
            )
            recover_expired(session)
            return list(
                session.scalars(
                    select(AIJob.id).where(
                        AIJob.owner == self.owner,
                        AIJob.status == "running",
                        AIJob.cancel_requested.is_(True),
                    )
                )
            )

    def claim(self):
        with self.factory() as session, session.begin():
            job = claim_job(session, self.owner, self.settings)
            return (job.id, job.claim_token) if job else None

    def release(self):
        with self.factory() as session, session.begin():
            session.execute(
                update(AIWorkerLease)
                .where(AIWorkerLease.owner == self.owner)
                .values(owner=None, expires_at=utcnow())
            )

    async def run(self, *, once=False, max_jobs=None):
        if not self.settings.ai_job_enabled:
            logger.info("worker_disabled")
            return
        if not await asyncio.to_thread(self.acquire):
            logger.warning("worker_already_active")
            return
        active = {}
        claimed = 0
        limit = 1 if once else max_jobs
        logger.info("worker_started concurrency=%d", self.settings.llm_max_concurrency)
        try:
            while not self.stop.is_set():
                cancelled = await asyncio.to_thread(self.heartbeat)
                if cancelled is None:
                    logger.error("worker_lease_lost")
                    break
                for job_id in cancelled:
                    if job_id in active and not active[job_id].cancelling():
                        active[job_id].cancel()
                for job_id, task in list(active.items()):
                    if task.done():
                        try:
                            task.result()
                        except (Exception, asyncio.CancelledError):
                            logger.error("worker_task_error job_id=%d", job_id)
                        del active[job_id]
                while len(active) < self.settings.llm_max_concurrency and (
                    limit is None or claimed < limit
                ):
                    job = await asyncio.to_thread(self.claim)
                    if job is None:
                        break
                    job_id, token = job
                    active[job_id] = asyncio.create_task(
                        self.orchestrator.process(job_id, self.owner, token)
                    )
                    claimed += 1
                    logger.info("job_claimed job_id=%d", job_id)
                if not active and (once or (limit is not None and claimed >= limit)):
                    break
                try:
                    await asyncio.wait_for(self.stop.wait(), timeout=self.settings.ai_poll_seconds)
                except TimeoutError:
                    continue
        finally:
            for task in active.values():
                if not task.cancelling():
                    task.cancel()
            if active:
                await asyncio.gather(*active.values(), return_exceptions=True)
            await asyncio.to_thread(self.release)
            logger.info("worker_stopped")


async def run_worker(once=False, max_jobs=None):
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = build_engine(settings.database_url)
    worker = Worker(sessionmaker(engine, expire_on_commit=False), settings)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, worker.stop.set)
    try:
        await worker.run(once=once, max_jobs=max_jobs)
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="CQA durable AI worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-jobs", type=int)
    args = parser.parse_args()
    asyncio.run(run_worker(args.once, args.max_jobs))


if __name__ == "__main__":
    main()

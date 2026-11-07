import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from app.ai.exceptions import AIError
from app.ai.jobs import acquire_worker, claim_job, recover_expired
from app.ai.orchestrator import AIOrchestrator, finish_success
from app.ai.output_parser import parse_evaluation
from app.ai.worker import Worker
from app.core.database import utcnow
from app.models import Evaluation
from app.models.ai import AIJob, AIWorkerLease
from tests.ai.conftest import FakeProvider, grounded_result


def enqueue(client, context, **kwargs):
    response = client.post(
        "/api/ai/evaluations", json={"conversation_id": context.conversation.id, **kwargs}
    )
    assert response.status_code == 202, response.text
    return response.json()


def claim(app, settings, owner="test-worker"):
    with app.state.session_factory() as session, session.begin():
        assert acquire_worker(session, owner, settings)
        job = claim_job(session, owner, settings)
        return job.id, job.claim_token


def test_idempotency_and_explicit_reevaluation(client, context):
    one = enqueue(client, context, idempotency_key="same")
    assert enqueue(client, context, idempotency_key="same")["id"] == one["id"]
    assert enqueue(client, context)["id"] != one["id"]
    assert (
        client.post(
            "/api/ai/evaluations",
            json={
                "conversation_id": context.conversation.id,
                "checklist_version_id": 1,
                "idempotency_key": "same",
            },
        ).status_code
        == 409
    )
    assert client.get("/api/ai/jobs?limit=1").json()["total"] == 2


def test_version_is_pinned_before_activation(client, context):
    first = enqueue(client, context, idempotency_key="pinned")
    configs = [
        c.model_dump(mode="json", exclude={"id", "checklist_version_id"})
        for c in context.checklist_version.criteria
    ]
    configs[0]["description"] = "A newly configured greeting condition"
    new = client.post("/api/checklists/1/versions", json={"criteria": configs}).json()
    assert (
        client.post("/api/checklists/1/activate", json={"version_id": new["id"]}).status_code == 200
    )
    assert enqueue(client, context)["checklist_version_id"] == new["id"]
    assert (
        enqueue(client, context, idempotency_key="pinned")["checklist_version_id"]
        == first["checklist_version_id"]
        == 1
    )


@pytest.mark.anyio
async def test_pipeline_persists_score_evidence_once_and_supports_appeal(
    app, client, context, ai_settings
):
    job = enqueue(client, context)
    jid, token = claim(app, ai_settings)
    orchestrator = AIOrchestrator(
        app.state.session_factory,
        ai_settings,
        provider_factory=lambda _: FakeProvider(grounded_result(context)),
    )
    eid = await orchestrator.process(jid, "test-worker", token)
    assert eid is not None
    response = client.get(f"/api/evaluations/{eid}").json()
    assert response["initial_score"] == response["final_score"] == "81.88"
    assert response["source"] == "ai"
    assert all(r["evidence"] for r in response["results"])
    assert (
        finish_success(
            app.state.session_factory,
            jid,
            "test-worker",
            token,
            parse_evaluation(grounded_result(context)),
            {},
        )
        is None
    )
    with app.state.session_factory() as session:
        assert session.scalar(select(func.count(Evaluation.id))) == 1
    state = client.get(f"/api/ai/jobs/{job['id']}").json()
    assert state["status"] == "completed" and state["evaluation_id"] == eid
    assert client.get(f"/api/ai/jobs/{jid}/attempts").json()["items"][0]["status"] == "completed"
    appeal = client.post(
        f"/api/evaluations/{eid}/appeals",
        json={"criterion_result_id": response["results"][0]["id"], "comment": "Please review"},
    )
    assert appeal.status_code == 201


@pytest.mark.anyio
async def test_retry_budget_and_manual_retry_preserve_attempts(app, client, context, ai_settings):
    job = enqueue(client, context)
    orchestrator = AIOrchestrator(
        app.state.session_factory,
        ai_settings,
        provider_factory=lambda _: FakeProvider(
            {}, error=AIError("provider_timeout", retryable=True)
        ),
    )
    for attempt in (1, 2):
        jid, token = claim(app, ai_settings)
        await orchestrator.process(jid, "test-worker", token)
        state = client.get(f"/api/ai/jobs/{job['id']}").json()
        assert state["status"] == ("queued" if attempt == 1 else "failed")
    assert client.post(f"/api/ai/jobs/{job['id']}/retry").json()["max_attempts"] == 4
    assert len(client.get(f"/api/ai/jobs/{job['id']}/attempts").json()["items"]) == 2


def test_queued_cancel_and_invalid_transitions(client, context):
    job = enqueue(client, context)
    url = f"/api/ai/jobs/{job['id']}"
    assert client.post(url + "/retry").status_code == 409
    assert client.post(url + "/cancel").json()["status"] == "cancelled"
    assert client.post(url + "/cancel").status_code == 409
    assert client.post("/api/ai/jobs/99999/cancel").status_code == 404


def test_running_cancellation_never_saves_evaluation(app, client, context, ai_settings):
    job = enqueue(client, context)
    jid, token = claim(app, ai_settings)
    state = client.post(f"/api/ai/jobs/{job['id']}/cancel").json()
    assert state["status"] == "running" and state["cancel_requested"]
    assert (
        finish_success(
            app.state.session_factory,
            jid,
            "test-worker",
            token,
            parse_evaluation(grounded_result(context)),
            {},
        )
        is None
    )
    assert client.get(f"/api/ai/jobs/{jid}").json()["status"] == "cancelled"
    with app.state.session_factory() as session:
        assert session.scalar(select(func.count(Evaluation.id))) == 0


def test_crash_recovery_rejects_stale_owner_and_claim(app, client, context, ai_settings):
    enqueue(client, context)
    jid, token = claim(app, ai_settings)
    with app.state.session_factory() as session, session.begin():
        assert not acquire_worker(session, "second-worker", ai_settings)
        assert claim_job(session, "second-worker", ai_settings) is None
        session.execute(
            update(AIJob)
            .where(AIJob.id == jid)
            .values(lease_expires_at=utcnow() - timedelta(seconds=1))
        )
        recover_expired(session)
    assert (
        finish_success(
            app.state.session_factory,
            jid,
            "test-worker",
            token,
            parse_evaluation(grounded_result(context)),
            {},
        )
        is None
    )
    jid2, token2 = claim(app, ai_settings)
    assert jid2 == jid and token2 != token
    assert (
        finish_success(
            app.state.session_factory,
            jid,
            "test-worker",
            token2,
            parse_evaluation(grounded_result(context)),
            {},
        )
        is not None
    )
    attempts = client.get(f"/api/ai/jobs/{jid}/attempts").json()["items"]
    assert [a["status"] for a in attempts] == ["interrupted", "completed"]


def test_batch_progress_filters_and_retry_failed(app, client, imported):
    data = {"dataset_id": imported[0]["dataset_id"], "idempotency_key": "batch"}
    batch = client.post("/api/ai/batches", json=data).json()
    assert batch["total"] == batch["queued"] == 3
    assert client.post("/api/ai/batches", json=data).json()["id"] == batch["id"]
    url = f"/api/ai/batches/{batch['id']}"
    jobs = client.get(url + "/jobs?limit=2").json()
    assert len(jobs["items"]) == 2 and jobs["total"] == 3
    jid = jobs["items"][0]["id"]
    client.post(f"/api/ai/jobs/{jid}/cancel")
    with app.state.session_factory() as session, session.begin():
        session.execute(
            update(AIJob).where(AIJob.id == jobs["items"][1]["id"]).values(status="failed")
        )
    state = client.get(url).json()
    assert state["percentage"] == "66.67" and state["failed"] == state["cancelled"] == 1
    assert client.post(url + "/retry-failed").json()["retried"] == 1
    assert client.get(url).json()["queued"] == 2
    assert client.post("/api/ai/batches", json={"language": "KZ"}).json()["total"] == 1
    assert client.get("/api/ai/batches").json()["total"] == 2


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"conversation_ids": []},
        {"conversation_ids": [1, 1]},
        {"conversation_ids": [1], "language": "RU"},
        {"language": "FR"},
        {"conversation_ids": [99999]},
    ],
)
def test_invalid_batch(client, payload):
    assert client.post("/api/ai/batches", json=payload).status_code in (404, 422)


@pytest.mark.anyio
async def test_worker_finishes_and_releases_lease(app, client, context, ai_settings):
    job = enqueue(client, context)
    worker = Worker(
        app.state.session_factory,
        ai_settings,
        orchestrator=AIOrchestrator(
            app.state.session_factory,
            ai_settings,
            provider_factory=lambda _: FakeProvider(grounded_result(context)),
        ),
    )
    await asyncio.wait_for(worker.run(once=True), 5)
    assert client.get(f"/api/ai/jobs/{job['id']}").json()["status"] == "completed"
    with app.state.session_factory() as session:
        assert session.get(AIWorkerLease, 1).owner is None


@pytest.mark.anyio
async def test_inflight_cancellation_aborts_provider(app, client, context, ai_settings):
    job = enqueue(client, context)
    entered = asyncio.Event()

    class WaitingProvider:
        async def generate_structured(self, *args):
            entered.set()
            await asyncio.sleep(30)

    worker = Worker(
        app.state.session_factory,
        ai_settings,
        orchestrator=AIOrchestrator(
            app.state.session_factory, ai_settings, provider_factory=lambda _: WaitingProvider()
        ),
    )
    task = asyncio.create_task(worker.run(once=True))
    await asyncio.wait_for(entered.wait(), 5)
    client.post(f"/api/ai/jobs/{job['id']}/cancel")
    await asyncio.wait_for(task, 5)
    assert client.get(f"/api/ai/jobs/{job['id']}").json()["status"] == "cancelled"


def test_public_manual_api_cannot_spoof_ai(client, evaluation_payload):
    evaluation_payload["source"] = "ai"
    assert client.post("/api/evaluations", json=evaluation_payload).status_code == 422


def test_atomic_failure_rolls_back_evaluation_and_job(
    app, client, context, ai_settings, monkeypatch
):
    from app.services.evaluation_service import EvaluationService

    enqueue(client, context)
    jid, token = claim(app, ai_settings)
    original = EvaluationService.create

    def fail_after_insert(service, submission):
        original(service, submission)
        raise RuntimeError("Simulated process failure before transaction commit")

    monkeypatch.setattr(EvaluationService, "create", fail_after_insert)
    with pytest.raises(RuntimeError):
        finish_success(
            app.state.session_factory,
            jid,
            "test-worker",
            token,
            parse_evaluation(grounded_result(context)),
            {},
        )
    with app.state.session_factory() as s:
        assert s.scalar(select(func.count(Evaluation.id))) == 0
        assert s.get(AIJob, jid).status == "running"


@pytest.mark.anyio
async def test_provider_down_does_not_disable_stage1(app, client, monkeypatch):
    class Down:
        async def health(self):
            return {"available": False, "model": "qwen3:4b", "error_code": "provider_connection"}

    monkeypatch.setattr("app.api.ai.make_provider", lambda _: Down())
    assert client.get("/api/health").status_code == 200
    result = client.get("/api/ai/health")
    assert result.status_code == 200 and not result.json()["provider"]["available"]
    assert not result.json()["worker"]["available"]


def test_batch_65_has_independent_jobs(client, dataset_payload):
    from copy import deepcopy

    from tests.conftest import upload

    original = dataset_payload["data"]["records"][0]
    dataset_payload["data"]["records"] = [deepcopy(original) for _ in range(65)]
    for i, row in enumerate(dataset_payload["data"]["records"]):
        row["conversation_id"] = f"synthetic-{i}"
    dataset_payload["data"]["total_records"] = 65
    dataset = upload(client, dataset_payload).json()["dataset"]
    batch = client.post("/api/ai/batches", json={"dataset_id": dataset["id"]}).json()
    jobs = client.get(f"/api/ai/batches/{batch['id']}/jobs?limit=100").json()
    assert batch["queued"] == 65 and jobs["total"] == 65
    assert len({j["conversation_id"] for j in jobs["items"]}) == 65
    client.post(f"/api/ai/jobs/{jobs['items'][0]['id']}/cancel")
    assert client.get(f"/api/ai/batches/{batch['id']}").json()["queued"] == 64


@pytest.mark.anyio
async def test_ai_critical_violation_is_separate_and_appeal_keeps_initial(
    app, client, context, ai_settings
):
    enqueue(client, context)
    jid, token = claim(app, ai_settings)
    data = grounded_result(context)
    data["results"][-1]["answer"] = "yes"
    data["results"][-1]["evidence"] = data["results"][0]["evidence"]
    orchestrator = AIOrchestrator(
        app.state.session_factory, ai_settings, provider_factory=lambda _: FakeProvider(data)
    )
    eid = await orchestrator.process(jid, "test-worker", token)
    detail = client.get(f"/api/evaluations/{eid}").json()
    assert detail["critical_violation"] is True and detail["final_score"] == "81.88"
    target = next(r for r in detail["results"] if r["criterion_code"] == "07")
    appeal = client.post(
        f"/api/evaluations/{eid}/appeals",
        json={"criterion_result_id": target["id"], "comment": "Review conclusion"},
    ).json()
    decision = client.post(
        f"/api/appeals/{appeal['id']}/decision",
        json={
            "decision": "revised",
            "revised_answer": "yes",
            "reason": "Reviewer checked the conclusion",
        },
    )
    assert decision.status_code == 200
    revised = client.get(f"/api/evaluations/{eid}").json()
    assert revised["initial_score"] == "81.88" and revised["final_score"] == "88.13"
    criterion = next(r for r in revised["results"] if r["id"] == target["id"])
    assert criterion["answer"] == "no" and criterion["current_answer"] == "yes"


def test_jobs_disabled_does_not_break_manual_api(app, client, context):
    app.state.settings.ai_job_enabled = False
    assert (
        client.post(
            "/api/ai/evaluations", json={"conversation_id": context.conversation.id}
        ).status_code
        == 503
    )
    assert client.get("/api/health").status_code == 200

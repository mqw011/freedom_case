from decimal import Decimal

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from alembic import command
from app.core.config import Settings
from app.core.database import build_engine
from app.core.exceptions import DomainError
from app.main import create_app
from app.models import ChecklistVersion, Conversation, Criterion, CriterionResult, Evaluation
from app.seed.default_checklist import ensure_default
from tests.conftest import BACKEND, migrate


def test_valid_quote_range_and_absence(client, evaluation_payload):
    messages = client.get(
        f"/api/conversations/{evaluation_payload['conversation_id']}/messages"
    ).json()
    evaluation_payload["results"][0]["evidence"] = [
        {
            "evidence_type": "quote",
            "message_id": messages[-1]["id"],
            "excerpt": "Здравствуйте!",
            "explanation": "Приветствие",
        },
        {
            "evidence_type": "range",
            "message_id": messages[0]["id"],
            "end_message_id": messages[-1]["id"],
            "explanation": "Весь диалог",
        },
        {"evidence_type": "absence", "explanation": "Действие отсутствует во всём диалоге"},
        {
            "evidence_type": "absence",
            "message_id": messages[0]["id"],
            "end_message_id": messages[1]["id"],
            "explanation": "Нет действия в диапазоне",
        },
    ]
    response = client.post("/api/evaluations", json=evaluation_payload)
    assert response.status_code == 201, response.text
    assert len(response.json()["results"][0]["evidence"]) == 4


@pytest.mark.parametrize(
    "failure", ["foreign", "missing", "reversed", "excerpt", "foreign_end", "shape"]
)
def test_evidence_integrity(client, evaluation_payload, imported, failure):
    messages = client.get(f"/api/conversations/{imported[0]['id']}/messages").json()
    other = client.get(f"/api/conversations/{imported[1]['id']}/messages").json()[0]
    evidence = {
        "evidence_type": "range",
        "message_id": messages[0]["id"],
        "end_message_id": messages[-1]["id"],
        "explanation": "Проверка",
    }
    if failure == "foreign":
        evidence["message_id"] = other["id"]
    elif failure == "missing":
        evidence["message_id"] = 999999
    elif failure == "reversed":
        evidence["message_id"], evidence["end_message_id"] = (
            evidence["end_message_id"],
            evidence["message_id"],
        )
    elif failure == "excerpt":
        evidence["excerpt"] = "Несуществующая цитата"
    elif failure == "foreign_end":
        evidence["end_message_id"] = other["id"]
    else:
        del evidence["message_id"]
    evaluation_payload["results"][0]["evidence"] = [evidence]
    assert client.post("/api/evaluations", json=evaluation_payload).status_code == 422
    assert client.get("/api/evaluations").json()["total"] == 0


@pytest.mark.parametrize(
    "model,field,value",
    [
        (ChecklistVersion, "status", "edited"),
        (Criterion, "weight", Decimal(99)),
        (CriterionResult, "answer", "yes"),
        (Evaluation, "initial_score", Decimal(42)),
        (Conversation, "language", "KZ"),
    ],
)
def test_orm_protects_snapshots(app, evaluation, model, field, value):
    with app.state.session_factory() as session:
        instance = session.scalar(select(model).order_by(model.id))
        if model is CriterionResult:
            value = "no"  # first criterion was yes
        setattr(instance, field, value)
        with pytest.raises(DomainError):
            session.flush()
        session.rollback()


def test_foreign_keys_enabled(app):
    with app.state.session_factory() as session:
        assert session.scalar(text("PRAGMA foreign_keys")) == 1
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO messages (conversation_id, message_index, speaker, "
                    "timestamp_raw, text) VALUES (999, 0, 'client', '00:00', 'Test')"
                )
            )
        session.rollback()


def test_optimistic_revision_detects_stale_update(app, evaluation):
    # Load/detach, then reattach after another transaction commits to model concurrent reviewers.
    with app.state.session_factory() as first:
        old = first.get(Evaluation, evaluation["id"])
        first.expunge(old)
    with app.state.session_factory() as second:
        current = second.get(Evaluation, evaluation["id"])
        current.revision += 1
        second.commit()
    with app.state.session_factory() as stale:
        stale.add(old)
        old.revision += 1
        with pytest.raises(StaleDataError):
            stale.flush()
        stale.rollback()


def test_migration_clean_install_roundtrip_and_seed_idempotence(tmp_path):
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    migrate(url)
    engine = build_engine(url)
    with Session(engine) as session:
        first = ensure_default(session)
        assert ensure_default(session).id == first.id
        session.commit()
        assert len(session.scalars(select(Criterion)).all()) == 8
        assert session.scalar(text("PRAGMA foreign_key_check")) is None
    engine.dispose()
    migrate(url, "base", downgrade=True)
    migrate(url)
    with TestClient(create_app(Settings(database_url=url, _env_file=None))) as client:
        assert client.get("/api/health").status_code == 200
        assert len(client.get("/api/checklists/1/versions").json()[0]["criteria"]) == 8


def test_migration_matches_models(app, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("DATABASE_URL", app.state.settings.database_url)
    get_settings.cache_clear()
    try:
        command.check(Config(str(BACKEND / "alembic.ini")))
    finally:
        get_settings.cache_clear()


def test_health_unmigrated_database_is_503(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'empty.db'}", _env_file=None))
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 503
        assert "Traceback" not in response.text


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://{group_id}.example.com/api",
        "https://user:pass@example.com/api",
        "https://example.com/{unknown}",
    ],
)
def test_configuration_rejects_unsafe_templates(url):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(dataset_api_url=url, _env_file=None)

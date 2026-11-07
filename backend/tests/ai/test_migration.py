from copy import deepcopy

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import build_engine
from app.main import create_app
from app.models import Message
from tests.conftest import migrate, upload


def test_stage1_upgrade_keeps_65_dialogues_1268_messages_and_snapshot(tmp_path, dataset_payload):
    url = f"sqlite:///{tmp_path / 'upgrade.db'}"
    migrate(url, "0002_default_checklist")
    records = []
    for i in range(65):
        record = deepcopy(dataset_payload["data"]["records"][0])
        record["conversation_id"] = f"synthetic-upgrade-{i}"
        record["transcript"] = [
            {
                "speaker": "operator",
                "timestamp": f"00:{j:02}",
                "text": f"Synthetic RU Русский KZ Қазақша EN message {j}",
            }
            for j in range(20 if i < 33 else 19)
        ]
        records.append(record)
    dataset_payload["data"].update(records=records, total_records=65)
    settings = Settings(database_url=url, _env_file=None)
    with TestClient(create_app(settings)) as client:
        assert upload(client, dataset_payload).status_code == 201
        cid = client.get("/api/conversations").json()["items"][0]["id"]
        answers = ["yes", "yes", "na", "15", "yes", "7", "no", "no"]
        payload = {
            "conversation_id": cid,
            "checklist_version_id": 1,
            "source": "test",
            "results": [
                {
                    "criterion_code": f"{i:02}",
                    "answer": answer,
                    "explanation": "Synthetic reference",
                }
                for i, answer in enumerate(answers, 1)
            ],
        }
        before = client.post("/api/evaluations", json=payload).json()
        assert before["initial_score"] == "81.88"
    engine = build_engine(url)
    with Session(engine) as session:
        messages = [
            tuple(row)
            for row in session.execute(
                select(
                    Message.id,
                    Message.conversation_id,
                    Message.message_index,
                    Message.speaker,
                    Message.timestamp_raw,
                    Message.text,
                ).order_by(Message.id)
            )
        ]
    assert len(messages) == 1268
    migrate(url)
    with Session(engine) as session:
        after = [
            tuple(row)
            for row in session.execute(
                select(
                    Message.id,
                    Message.conversation_id,
                    Message.message_index,
                    Message.speaker,
                    Message.timestamp_raw,
                    Message.text,
                ).order_by(Message.id)
            )
        ]
        assert after == messages
        assert session.scalar(text("PRAGMA foreign_key_check")) is None
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/conversations").json()["total"] == 65
        assert client.get(f"/api/evaluations/{before['id']}").json() == before
        job = client.post("/api/ai/evaluations", json={"conversation_id": cid}).json()
        assert job["status"] == "queued" and job["checklist_version_id"] == 1
    engine.dispose()

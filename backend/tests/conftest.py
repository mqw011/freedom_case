import copy
import json
import os
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command
from app.core.config import Settings, get_settings
from app.main import create_app

BACKEND = Path(__file__).resolve().parents[1]


def migrate(url, revision="head", *, downgrade=False):
    with patch.dict(os.environ, {"DATABASE_URL": url}):
        get_settings.cache_clear()
        config = Config(str(BACKEND / "alembic.ini"))
        try:
            (command.downgrade if downgrade else command.upgrade)(config, revision)
        finally:
            get_settings.cache_clear()


@pytest.fixture(scope="session")
def migrated_template(tmp_path_factory):
    path = tmp_path_factory.mktemp("template") / "template.db"
    migrate(f"sqlite:///{path}")
    return path


@pytest.fixture
def app(tmp_path, migrated_template):
    path = tmp_path / "test.db"
    shutil.copyfile(migrated_template, path)
    return create_app(Settings(database_url=f"sqlite:///{path}", _env_file=None))


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def dataset_payload():
    return {
        "error": "",
        "isSuccess": True,
        "data": {
            "dataset_group_id": "LOCAL-TEST",
            "total_records": 3,
            "records": [
                {
                    "conversation_id": "synthetic-ru",
                    "channel": "agent chat",
                    "language": "RU",
                    "audio_url": None,
                    "transcript": [
                        {"timestamp": "00:00", "speaker": "system", "text": "Начало"},
                        {"timestamp": "00:01", "speaker": "bot", "text": "Добро пожаловать"},
                        {"timestamp": "00:02", "speaker": "client", "text": "Какой тариф?"},
                        {
                            "timestamp": "04:05",
                            "speaker": "operator",
                            "text": "Здравствуйте! Я Анна.",
                        },
                    ],
                },
                {
                    "conversation_id": "synthetic-kz",
                    "channel": "agent chat",
                    "language": "KZ",
                    "audio_url": None,
                    "transcript": [
                        {"timestamp": "00:01", "speaker": "operator", "text": "Сәлеметсіз бе!"}
                    ],
                },
                {
                    "conversation_id": "synthetic-en",
                    "channel": "voice call",
                    "language": "EN",
                    "audio_url": "https://example.invalid/synthetic-call.wav",
                    "transcript": [
                        {
                            "timestamp": "2026-01-01T12:00:00+05:00",
                            "speaker": "client",
                            "text": "Hello",
                        },
                        {
                            "timestamp": "2026-01-01T07:00:05Z",
                            "speaker": "operator",
                            "text": "Hello, I am Alex",
                        },
                    ],
                },
            ],
        },
    }


def upload(client, payload):
    return client.post(
        "/api/datasets/import-json",
        files={
            "file": (
                "synthetic.json",
                json.dumps(payload, ensure_ascii=False).encode(),
                "application/json",
            )
        },
    )


@pytest.fixture
def imported(client, dataset_payload):
    response = upload(client, dataset_payload)
    assert response.status_code == 201, response.text
    return client.get("/api/conversations").json()["items"]


@pytest.fixture
def evaluation_payload(imported):
    answers = {
        "01": "yes",
        "02": "yes",
        "03": "na",
        "04": "15",
        "05": "yes",
        "06": "7",
        "07": "no",
        "08": "no",
    }
    return {
        "conversation_id": imported[0]["id"],
        "checklist_version_id": 1,
        "source": "test",
        "results": [
            {"criterion_code": code, "answer": answer, "explanation": "Ручная проверка"}
            for code, answer in answers.items()
        ],
    }


@pytest.fixture
def evaluation(client, evaluation_payload):
    response = client.post("/api/evaluations", json=evaluation_payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def mock_dataset_api(dataset_payload):
    state = {"payload": copy.deepcopy(dataset_payload), "status": 200, "body": None, "requests": []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["requests"].append(self.path)
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            if state["status"] == 302:
                self.send_header("Location", "/do-not-follow")
            self.end_headers()
            self.wfile.write(
                state["body"]
                if state["body"] is not None
                else json.dumps(state["payload"]).encode()
            )

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state["url"] = f"http://127.0.0.1:{server.server_port}/dataset"
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

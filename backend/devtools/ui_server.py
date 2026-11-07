"""Isolated synthetic UI sandbox. Never opens, copies or modifies the DEV database."""

import argparse
import json
import os
import tempfile
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import uvicorn
from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command
from app.core.config import Settings, get_settings


def payload(group="SYNTHETIC-UI", count=65):
    records = []
    for index in range(count):
        language = ["RU", "KZ", "EN"][index % 3]
        voice = index % 13 == 12
        texts = {
            "RU": [
                "Тест: начало",
                "Тестовый бот",
                "Как открыть учебный счёт?",
                "Здравствуйте! Я Анна. Это синтетический пример.",
                "Откройте учебный раздел.\nВыберите «Демо-счёт».",
                "Спасибо!",
            ],
            "KZ": [
                "Тест: басталуы",
                "Тест бот",
                "Оқу шотын қалай ашуға болады?",
                "Сәлеметсіз бе! Менің атым Айдана.",
                "Оқу бөлімін таңдаңыз.",
                "Рақмет!",
            ],
            "EN": [
                "Test: started",
                "Test bot",
                "How do I open a practice account?",
                "Hello! I am Alex. This is synthetic data.",
                "Open the training section and select Demo account.",
                "Thank you!",
            ],
        }[language]
        length = 115 if index == 0 else 6
        transcript = []
        for j in range(length):
            timestamp = (
                (
                    datetime.fromisoformat("2026-01-01T12:00:00+05:00") + timedelta(seconds=j * 10)
                ).isoformat()
                if voice
                else f"{j // 6:02d}:{(j % 6) * 10:02d}"
            )
            transcript.append(
                {
                    "timestamp": timestamp,
                    "speaker": ["system", "bot", "client", "operator", "operator", "client"][j % 6],
                    "text": texts[j % 6]
                    if j < 6
                    else f"Синтетическая реплика {j + 1}: оқу / test.",
                }
            )
        records.append(
            {
                "conversation_id": f"{group}-{index + 1:03d}",
                "language": language,
                "channel": "voice call" if voice else "agent chat",
                "transcript": transcript,
                "audio_url": "https://example.invalid/synthetic-audio.wav" if voice else None,
            }
        )
    return {
        "error": "",
        "isSuccess": True,
        "data": {"dataset_group_id": group, "total_records": count, "records": records},
    }


class SyntheticOrganizer(BaseHTTPRequestHandler):
    def do_GET(self):
        group = parse_qs(urlsplit(self.path).query).get("group_id", ["CONTROL-UI"])[0]
        if group == "FAIL-UI":
            self.send_error(503)
            return
        body = json.dumps(payload(group, 2), ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def seed(app):
    # Use the same HTTP endpoints the browser uses. No AI results are fabricated.
    with TestClient(app) as client:
        imported = client.post(
            "/api/datasets/import-json",
            files={"file": ("synthetic.json", json.dumps(payload()), "application/json")},
        )
        assert imported.status_code == 201
        for cid in (1, 2):
            messages = client.get(f"/api/conversations/{cid}").json()["messages"]
            answers = ["yes", "yes", "na", "15", "yes", "7", "no", "no"]
            if cid == 2:
                # Explicit test labels, not claims about Qwen quality.
                answers = ["yes", "na", "na", "20", "yes", "10", "yes", "yes"]
            results = []
            for i, answer in enumerate(answers):
                evidence = {
                    "evidence_type": "quote",
                    "message_id": messages[3]["id"],
                    "excerpt": messages[3]["text"],
                    "explanation": "Учебная цитата",
                }
                if i == 2:
                    evidence = {
                        "evidence_type": "range",
                        "message_id": messages[2]["id"],
                        "end_message_id": messages[4]["id"],
                        "explanation": "Учебный контекст N/A",
                    }
                if i in (6, 7):
                    evidence = {
                        "evidence_type": "absence",
                        "message_id": messages[-2]["id"],
                        "end_message_id": messages[-1]["id"],
                        "explanation": "Проверен конец учебного разговора",
                    }
                results.append(
                    {
                        "criterion_code": f"{i + 1:02d}",
                        "answer": answer,
                        "explanation": "Тестовая ручная разметка для проверки интерфейса.",
                        "evidence": [evidence],
                    }
                )
            response = client.post(
                "/api/evaluations",
                json={
                    "conversation_id": cid,
                    "checklist_version_id": 1,
                    "source": "test",
                    "results": results,
                },
            )
            assert response.status_code == 201
        # Real queued jobs only, no worker and no inference. Retry/failure states are tested
        # separately with deterministic test fixtures and backend regression tests.
        assert client.post("/api/ai/evaluations", json={"conversation_id": 3}).status_code == 202

        for ids in ([4, 5], [6, 7]):
            batch_response = client.post("/api/ai/batches", json={"conversation_ids": ids})
            assert batch_response.status_code == 202
            jobs = client.get(f"/api/ai/batches/{batch_response.json()['id']}/jobs").json()["items"]
            # Deliberately synthetic failure fixture for UI retry controls. No inference claimed.
            from app.core.database import utcnow
            from app.models.ai import AIJob, AIJobAttempt

            with app.state.session_factory.begin() as session:
                job = session.get(AIJob, jobs[0]["id"])
                job.status = "failed"
                job.attempts = 1
                job.started_at = job.completed_at = utcnow()
                job.error_code = "synthetic_test_failure"
                job.safe_error_message = "Синтетическая ошибка для проверки кнопки Retry."
                session.add(
                    AIJobAttempt(
                        job_id=job.id,
                        attempt_number=1,
                        status="failed",
                        started_at=job.started_at,
                        finished_at=job.completed_at,
                        error_code=job.error_code,
                    )
                )
            assert client.post(f"/api/ai/jobs/{jobs[1]['id']}/cancel").status_code == 200


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8011)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="cqa-ui-synthetic-") as temp:
        url = f"sqlite:///{Path(temp) / 'synthetic.db'}"
        # Override all sensitive endpoints before app import; .env is never copied or edited.
        os.environ.update(
            DATABASE_URL=url,
            AI_AUTO_START_WORKER="false",
            LLM_BASE_URL="http://127.0.0.1:1/v1",
            DATASET_API_URL="",
            LLM_API_KEY="",
            LLM_ALLOW_REMOTE="false",
            LOG_LEVEL="WARNING",
        )
        get_settings.cache_clear()
        command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
        from app.main import create_app

        organizer = ThreadingHTTPServer(("127.0.0.1", 0), SyntheticOrganizer)
        threading.Thread(target=organizer.serve_forever, daemon=True).start()
        settings = Settings(
            _env_file=None,
            database_url=url,
            app_env="ui-synthetic",
            cors_origins="http://127.0.0.1:4173,http://localhost:4173",
            dataset_api_url=f"http://127.0.0.1:{organizer.server_port}/dataset",
            llm_base_url="http://127.0.0.1:1/v1",
            llm_timeout=1,
            ai_auto_start_worker=False,
            log_level="WARNING",
        )
        app = create_app(settings)
        seed(app)
        print(f"Synthetic UI sandbox on 127.0.0.1:{args.port}; DEV database is untouched.")
        try:
            uvicorn.run(
                app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning"
            )
        finally:
            organizer.shutdown()
            organizer.server_close()


if __name__ == "__main__":
    main()

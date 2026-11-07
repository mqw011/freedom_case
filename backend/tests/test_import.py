import copy

import httpx
import pytest
from sqlalchemy import func, select

from app.models import Conversation, Message
from tests.conftest import upload


def test_json_import_retains_all_data(client, dataset_payload, app):
    report = upload(client, dataset_payload).json()
    assert report["inserted"] == 3 and report["received_records"] == 3
    assert report["dataset"]["total_records"] == 3
    conversations = client.get("/api/conversations").json()["items"]
    for conversation, original in zip(
        conversations, dataset_payload["data"]["records"], strict=True
    ):
        detail = client.get(f"/api/conversations/{conversation['id']}").json()
        assert detail["language"] == original["language"]
        assert detail["channel"] == original["channel"]
        assert detail["audio_url"] == original["audio_url"]
        for index, (message, source) in enumerate(
            zip(detail["messages"], original["transcript"], strict=True)
        ):
            assert message["message_index"] == index
            assert message["timestamp_raw"] == source["timestamp"]
            assert message["speaker"] == source["speaker"]
            assert message["text"] == source["text"]
    again = upload(client, dataset_payload)
    assert again.status_code == 201
    assert again.json()["skipped"] == 3 and again.json()["inserted"] == 0
    with app.state.session_factory() as session:
        assert session.scalar(select(func.count(Conversation.id))) == 3
        assert session.scalar(select(func.count(Message.id))) == 7
    assert client.get("/api/datasets").json()["total"] == 1
    assert client.get(f"/api/datasets/{report['dataset']['id']}").json()["group_id"] == "LOCAL-TEST"


def test_declared_count_is_not_trusted(client, dataset_payload):
    dataset_payload["data"]["total_records"] = 65
    report = upload(client, dataset_payload).json()
    assert report["declared_records"] == 65 and report["received_records"] == 3
    assert report["warnings"]
    assert report["dataset"]["total_records"] == 3


def test_empty_dataset(client, dataset_payload):
    dataset_payload["data"].update(records=[], total_records=0)
    response = upload(client, dataset_payload)
    assert response.status_code == 201
    assert response.json()["inserted"] == 0
    assert client.get("/api/conversations").json()["total"] == 0


def test_group_scoped_identity_and_incremental_import(client, dataset_payload):
    assert upload(client, dataset_payload).status_code == 201
    additional = copy.deepcopy(dataset_payload["data"]["records"][0])
    additional["conversation_id"] = "new-conversation"
    dataset_payload["data"]["records"].append(additional)
    assert upload(client, dataset_payload).json()["inserted"] == 1
    assert client.get("/api/datasets/1").json()["total_records"] == 4
    dataset_payload["data"]["dataset_group_id"] = "CONTROL-1"
    assert upload(client, dataset_payload).json()["inserted"] == 4
    assert client.get("/api/datasets").json()["total"] == 2
    assert client.get("/api/conversations").json()["total"] == 8


def test_changed_content_conflicts_and_rolls_back_entire_batch(client, dataset_payload):
    upload(client, dataset_payload)
    new = copy.deepcopy(dataset_payload["data"]["records"][0])
    new["conversation_id"] = "must-rollback"
    dataset_payload["data"]["records"].insert(0, new)
    dataset_payload["data"]["records"][-1]["transcript"][0]["text"] = "Changed transcript"
    assert upload(client, dataset_payload).status_code == 409
    assert client.get("/api/conversations").json()["total"] == 3
    assert client.get("/api/datasets/1").json()["total_records"] == 3


@pytest.mark.parametrize(
    "field,value",
    [
        ("language", "FR"),
        ("channel", "email"),
        ("conversation_id", ""),
        ("transcript", []),
        ("audio_url", "file:///secret"),
        ("audio_url", "https://example.org/a"),
    ],
)
def test_invalid_records(client, dataset_payload, field, value):
    dataset_payload["data"]["records"][0][field] = value
    assert upload(client, dataset_payload).status_code == 422
    assert client.get("/api/datasets").json()["total"] == 0


@pytest.mark.parametrize(
    "field,value",
    [("speaker", "agent"), ("timestamp", "00:65"), ("timestamp", "2026-01-01"), ("text", "")],
)
def test_invalid_messages(client, dataset_payload, field, value):
    dataset_payload["data"]["records"][0]["transcript"][0][field] = value
    assert upload(client, dataset_payload).status_code == 422


@pytest.mark.parametrize("timestamp", ["00:05", "2026-01-01T10:00:00", "garbage"])
def test_calls_require_timezone(client, dataset_payload, timestamp):
    dataset_payload["data"]["records"][2]["transcript"][0]["timestamp"] = timestamp
    assert upload(client, dataset_payload).status_code == 422


def test_missing_id_and_duplicate_records(client, dataset_payload):
    invalid = copy.deepcopy(dataset_payload)
    del invalid["data"]["records"][0]["conversation_id"]
    assert upload(client, invalid).status_code == 422
    dataset_payload["data"]["records"].append(dataset_payload["data"]["records"][0])
    assert upload(client, dataset_payload).status_code == 422


def test_invalid_json_and_missing_file(client):
    response = client.post(
        "/api/datasets/import-json", files={"file": ("bad.json", b"{", "application/json")}
    )
    assert response.status_code == 400
    assert client.post("/api/datasets/import-json").status_code == 422


def test_file_size_limit(client, app, dataset_payload):
    app.state.settings.import_max_bytes = 10
    assert upload(client, dataset_payload).status_code == 422


@pytest.mark.parametrize("group", ["", "../DEV", "https://localhost", "DEV?x=y", "a" * 65])
def test_invalid_group_and_no_open_proxy(client, group):
    assert client.post("/api/datasets/import", json={"group_id": group}).status_code == 422
    assert (
        client.post("/api/datasets/import", json={"group_id": "DEV", "url": group}).status_code
        == 422
    )


def test_unconfigured_api(client):
    response = client.post("/api/datasets/import", json={"group_id": "DEV"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dataset_not_configured"


@pytest.mark.parametrize("template", [False, True])
def test_real_local_http_import(client, app, mock_dataset_api, template):
    app.state.settings.dataset_api_url = mock_dataset_api["url"] + (
        "/{group_id}" if template else ""
    )
    response = client.post("/api/datasets/import", json={"group_id": "LOCAL-TEST"})
    assert response.status_code == 201, response.text
    assert response.json()["inserted"] == 3
    expected = "/dataset/LOCAL-TEST" if template else "/dataset?group_id=LOCAL-TEST"
    assert mock_dataset_api["requests"] == [expected]
    assert (
        client.post("/api/datasets/import", json={"group_id": "LOCAL-TEST"}).json()["skipped"] == 3
    )


@pytest.mark.parametrize(
    "failure", ["http", "redirect", "json", "structure", "success", "error", "group", "size"]
)
def test_upstream_errors_are_safe(client, app, mock_dataset_api, failure):
    app.state.settings.dataset_api_url = mock_dataset_api["url"]
    if failure == "http":
        mock_dataset_api["status"] = 500
    elif failure == "redirect":
        mock_dataset_api["status"] = 302
    elif failure == "json":
        mock_dataset_api["body"] = b"not-json secret-token"
    elif failure == "structure":
        mock_dataset_api["payload"] = {"isSuccess": True}
    elif failure == "success":
        mock_dataset_api["payload"] = {"isSuccess": False, "error": "secret-token"}
    elif failure == "error":
        mock_dataset_api["payload"]["error"] = "secret-token"
    elif failure == "group":
        mock_dataset_api["payload"]["data"]["dataset_group_id"] = "WRONG"
    else:
        app.state.settings.import_max_bytes = 10
    response = client.post("/api/datasets/import", json={"group_id": "LOCAL-TEST"})
    assert response.status_code == 502
    assert "secret-token" not in response.text
    assert len(mock_dataset_api["requests"]) == 1
    assert client.get("/api/datasets").json()["total"] == 0


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
def test_network_failures(client, app, monkeypatch, error):
    app.state.settings.dataset_api_url = "http://127.0.0.1:1/dataset"

    def fail(*args, **kwargs):
        raise error("secret-token")

    monkeypatch.setattr(httpx.Client, "stream", fail)
    response = client.post("/api/datasets/import", json={"group_id": "DEV"})
    assert response.status_code == 502
    assert "secret-token" not in response.text

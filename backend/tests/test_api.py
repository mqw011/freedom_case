import copy
from decimal import Decimal

import pytest

from app.seed.default_checklist import default_checklist


def test_health_openapi_and_cors(client):
    assert client.get("/api/health").json() == {"status": "ok", "database": "ok"}
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert "/api/appeals/{appeal_id}/decision" in schema["paths"]
    assert "StructuredCriterionResult" in schema["components"]["schemas"]
    response = client.options(
        "/api/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_list_filter_pagination_and_detail(client, imported):
    page = client.get("/api/conversations?limit=1&offset=1").json()
    assert page["total"] == 3 and page["items"][0]["language"] == "KZ"
    assert page["offset"] == 1 and page["limit"] == 1
    assert client.get("/api/conversations?language=RU").json()["total"] == 1
    assert client.get("/api/conversations?channel=voice%20call").json()["total"] == 1
    assert client.get("/api/conversations?dataset_id=999").json()["total"] == 0
    assert client.get("/api/conversations?search=synthetic-en").json()["total"] == 1
    assert client.get("/api/conversations?search=%25").json()["total"] == 0
    assert client.get("/api/conversations?offset=100").json()["items"] == []
    detail = client.get(f"/api/conversations/{imported[0]['id']}").json()
    messages = client.get(f"/api/conversations/{imported[0]['id']}/messages").json()
    assert detail["messages"] == messages
    assert len(messages) == 4


@pytest.mark.parametrize(
    "query", ["limit=0", "limit=101", "offset=-1", "language=FR", "channel=email"]
)
def test_invalid_filters(client, query):
    assert client.get(f"/api/conversations?{query}").status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "datasets",
        "conversations",
        "conversations/999/messages",
        "checklists",
        "checklists/999/versions",
        "evaluations",
        "appeals",
    ],
)
def test_not_found(client, path):
    endpoint = f"/api/{path}" if "/999/" in path else f"/api/{path}/999"
    assert client.get(endpoint).status_code == 404


def test_exact_seed_and_create_checklist(client):
    checklist = client.get("/api/checklists").json()["items"][0]
    assert checklist["active_version_id"] == 1
    version = client.get("/api/checklists/1/versions").json()[0]
    expected = default_checklist().version.model_dump(mode="json")["criteria"]
    for actual, config in zip(version["criteria"], expected, strict=True):
        assert {k: actual[k] for k in config} == config
    assert len(version["criteria"]) == 8
    payload = default_checklist().model_dump(mode="json")
    payload["name"] = "Custom checklist"
    response = client.post("/api/checklists", json=payload)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["id"] != 1 and created["active_version_id"] != 1
    assert client.get(f"/api/checklists/{created['id']}").json()["name"] == "Custom checklist"
    assert (
        client.post(
            "/api/checklists/1/activate", json={"version_id": created["active_version_id"]}
        ).status_code
        == 422
    )


def test_manual_evaluation_get_lists_and_no_ai_stub(client, evaluation, evaluation_payload):
    assert evaluation["initial_score"] == evaluation["final_score"] == "81.88"
    assert evaluation["status"] == "completed" and evaluation["source"] == "test"
    assert not evaluation["critical_violation"]
    result = next(r for r in evaluation["results"] if r["criterion_code"] == "06")
    assert Decimal(result["weighted_score"]) == Decimal("10.5")
    assert client.get(f"/api/evaluations/{evaluation['id']}").json() == evaluation
    assert client.get("/api/evaluations?source=test").json()["total"] == 1
    assert (
        client.get(f"/api/conversations/{evaluation['conversation_id']}/evaluations").json()[
            "total"
        ]
        == 1
    )
    evaluation_payload["source"] = "ai"
    assert client.post("/api/evaluations", json=evaluation_payload).status_code == 422


@pytest.mark.parametrize(
    "failure", ["missing", "duplicate", "unknown", "scale", "na", "binary", "boolean"]
)
def test_invalid_evaluation_results(client, evaluation_payload, failure):
    if failure == "missing":
        evaluation_payload["results"].pop()
    elif failure == "duplicate":
        evaluation_payload["results"].append(evaluation_payload["results"][0])
    elif failure == "unknown":
        evaluation_payload["results"][0]["criterion_code"] = "99"
    elif failure == "scale":
        evaluation_payload["results"][3]["answer"] = 12
    elif failure == "na":
        evaluation_payload["results"][0]["answer"] = "na"
    elif failure == "binary":
        evaluation_payload["results"][0]["answer"] = 1
    else:
        evaluation_payload["results"][0]["answer"] = True
    assert client.post("/api/evaluations", json=evaluation_payload).status_code == 422
    assert client.get("/api/evaluations").json()["total"] == 0


@pytest.mark.parametrize("field", ["checklist_version_id", "conversation_id"])
def test_invalid_evaluation_references(client, evaluation_payload, field):
    evaluation_payload[field] = 999
    assert client.post("/api/evaluations", json=evaluation_payload).status_code == 404


def test_version_activation_does_not_change_old_evaluation(client, evaluation, evaluation_payload):
    initial = copy.deepcopy(evaluation)
    payload = default_checklist().version.model_dump(mode="json")
    payload["criteria"][0]["weight"] = "20"
    payload["criteria"][1]["weight"] = "5"
    payload["criteria"][5]["allowed_values"] = [0, 3, 9]
    payload["criteria"][5]["max_score"] = 9
    payload["criteria"][5]["scale_labels"] = {}
    payload["criteria"][0]["title"] = "Updated contact"
    version = client.post("/api/checklists/1/versions", json=payload)
    assert version.status_code == 201, version.text
    version_id = version.json()["id"]
    assert version.json()["version_number"] == 2
    assert (
        client.post("/api/checklists/1/activate", json={"version_id": version_id}).status_code
        == 200
    )
    assert client.get("/api/checklists/1").json()["active_version_id"] == version_id
    assert client.get(f"/api/evaluations/{evaluation['id']}").json() == initial
    versions = client.get("/api/checklists/1/versions").json()
    assert versions[0]["criteria"][0]["weight"] == "10"
    assert versions[1]["criteria"][0]["weight"] == "20"
    evaluation_payload["checklist_version_id"] = version_id
    assert client.post("/api/evaluations", json=evaluation_payload).status_code == 422
    evaluation_payload["results"][5]["answer"] = 3
    assert client.post("/api/evaluations", json=evaluation_payload).status_code == 201


def test_unbalanced_version_saved_but_not_activated_or_scored(client, evaluation_payload):
    payload = default_checklist().version.model_dump(mode="json")
    payload["criteria"][0]["weight"] = 50
    response = client.post("/api/checklists/1/versions", json=payload)
    assert response.status_code == 201
    version_id = response.json()["id"]
    assert (
        client.post("/api/checklists/1/activate", json={"version_id": version_id}).status_code
        == 422
    )
    evaluation_payload["checklist_version_id"] = version_id
    assert client.post("/api/evaluations", json=evaluation_payload).status_code == 422
    assert client.get("/api/checklists/1").json()["active_version_id"] == 1


@pytest.mark.parametrize("change", ["negative", "scale", "duplicate", "order", "na", "flag"])
def test_invalid_checklist_versions(client, change):
    data = default_checklist().version.model_dump(mode="json")
    if change == "negative":
        data["criteria"][0]["weight"] = -1
    elif change == "scale":
        data["criteria"][3]["max_score"] = 19
    elif change == "duplicate":
        data["criteria"][1]["code"] = "01"
    elif change == "order":
        data["criteria"][1]["display_order"] = 1
    elif change == "na":
        data["criteria"][0]["allow_na"] = True
    else:
        data["criteria"][7]["weight"] = 10
    assert client.post("/api/checklists/1/versions", json=data).status_code == 422
    assert len(client.get("/api/checklists/1/versions").json()) == 1

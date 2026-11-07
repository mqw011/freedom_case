import pytest


def submit(client, evaluation, code="07"):
    result = next(r for r in evaluation["results"] if r["criterion_code"] == code)
    return client.post(
        f"/api/evaluations/{evaluation['id']}/appeals",
        json={
            "criterion_result_id": result["id"],
            "comment": "Прошу пересмотреть критерий",
        },
    )


def revise(client, appeal_id, answer):
    return client.post(
        f"/api/appeals/{appeal_id}/decision",
        json={
            "decision": "revised",
            "revised_answer": answer,
            "reason": "Проверены реплики диалога",
        },
    )


def test_appeal_recalculation_and_immutable_initial_result(client, evaluation):
    response = submit(client, evaluation)
    assert response.status_code == 201
    appeal_id = response.json()["id"]
    assert response.json()["status"] == "pending"
    assert client.get("/api/appeals?status=pending").json()["total"] == 1
    assert client.get(f"/api/appeals/{appeal_id}").json() == response.json()
    decided = revise(client, appeal_id, "yes")
    assert decided.status_code == 200, decided.text
    decision = decided.json()["decision"]
    assert decided.json()["status"] == "revised"
    assert decision["original_answer"] == "no" and decision["revised_answer"] == "yes"
    assert decision["original_score"] == "0" and decision["revised_score"] == "5"
    assert decision["original_final_score"] == "81.88"
    assert decision["revised_final_score"] == "88.13"
    current = client.get(f"/api/evaluations/{evaluation['id']}").json()
    assert current["initial_score"] == "81.88" and current["final_score"] == "88.13"
    old = next(r for r in evaluation["results"] if r["criterion_code"] == "07")
    result = next(r for r in current["results"] if r["criterion_code"] == "07")
    assert result["answer"] == old["answer"] == "no"
    assert result["weighted_score"] == old["weighted_score"] == "0"
    assert result["current_answer"] == "yes" and result["current_weighted_score"] == "5"
    assert current["revision"] > evaluation["revision"]
    assert current["appeal_ids"] == [appeal_id]
    assert client.get("/api/appeals?status=pending").json()["total"] == 0


def test_uphold_and_closed_appeal(client, evaluation):
    appeal_id = submit(client, evaluation).json()["id"]
    payload = {"decision": "upheld", "reason": "Исходная оценка подтверждена"}
    assert client.post(f"/api/appeals/{appeal_id}/decision", json=payload).status_code == 200
    assert client.get(f"/api/evaluations/{evaluation['id']}").json()["final_score"] == "81.88"
    assert client.post(f"/api/appeals/{appeal_id}/decision", json=payload).status_code == 409
    assert revise(client, appeal_id, "yes").status_code == 409


def test_repeat_appeals_preserve_history(client, evaluation):
    first = submit(client, evaluation).json()["id"]
    assert submit(client, evaluation).status_code == 409
    assert revise(client, first, "yes").status_code == 200
    second = submit(client, evaluation).json()["id"]
    assert second != first
    decision = revise(client, second, "na").json()["decision"]
    assert decision["original_answer"] == "yes"
    assert decision["original_final_score"] == "88.13"
    assert decision["revised_answer"] == "na" and decision["revised_score"] is None
    current = client.get(f"/api/evaluations/{evaluation['id']}").json()
    assert current["initial_score"] == "81.88" and current["final_score"] == "87.33"
    assert current["appeal_ids"] == [first, second]
    assert client.get(f"/api/appeals/{first}").json()["decision"]["revised_answer"] == "yes"


def test_multiple_criterion_decisions_accumulate(client, evaluation):
    closing = submit(client, evaluation, "07").json()["id"]
    consultation = submit(client, evaluation, "04").json()["id"]
    assert revise(client, closing, "yes").status_code == 200
    assert revise(client, consultation, 20).status_code == 200
    current = client.get(f"/api/evaluations/{evaluation['id']}").json()
    assert current["final_score"] == "94.38"
    assert current["initial_score"] == "81.88"


def test_critical_violation_revision_is_separate(client, evaluation):
    appeal_id = submit(client, evaluation, "08").json()["id"]
    assert revise(client, appeal_id, "yes").status_code == 200
    current = client.get(f"/api/evaluations/{evaluation['id']}").json()
    assert current["critical_violation"] and not current["initial_critical_violation"]
    assert current["final_score"] == current["initial_score"] == "81.88"


@pytest.mark.parametrize(
    "payload",
    [
        {"decision": "revised", "revised_answer": "yes"},
        {"decision": "revised", "revised_answer": "yes", "reason": " "},
        {"decision": "revised", "reason": "Reason"},
        {"decision": "upheld", "revised_answer": "yes", "reason": "Reason"},
        {"decision": "revised", "revised_answer": 12, "reason": "Reason"},
        {"decision": "revised", "revised_answer": "no", "reason": "Reason"},
    ],
)
def test_invalid_decisions_leave_appeal_pending(client, evaluation, payload):
    appeal_id = submit(client, evaluation).json()["id"]
    assert client.post(f"/api/appeals/{appeal_id}/decision", json=payload).status_code == 422
    assert client.get(f"/api/appeals/{appeal_id}").json()["status"] == "pending"
    assert client.get(f"/api/evaluations/{evaluation['id']}").json()["final_score"] == "81.88"


def test_forbidden_na_on_revision(client, evaluation):
    appeal_id = submit(client, evaluation, "01").json()["id"]
    assert revise(client, appeal_id, "na").status_code == 422


def test_invalid_appeal_references(client, evaluation, evaluation_payload):
    assert (
        client.post(
            "/api/evaluations/999/appeals",
            json={
                "criterion_result_id": evaluation["results"][0]["id"],
                "comment": "Reason",
            },
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/evaluations/{evaluation['id']}/appeals",
            json={
                "criterion_result_id": 999,
                "comment": "Reason",
            },
        ).status_code
        == 404
    )
    other = client.post("/api/evaluations", json=evaluation_payload).json()
    assert (
        client.post(
            f"/api/evaluations/{evaluation['id']}/appeals",
            json={
                "criterion_result_id": other["results"][0]["id"],
                "comment": "Reason",
            },
        ).status_code
        == 422
    )
    assert revise(client, 999, "yes").status_code == 404

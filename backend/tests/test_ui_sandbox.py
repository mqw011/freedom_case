from devtools.ui_server import seed


def test_synthetic_sandbox_uses_real_services_without_fake_ai(client, app):
    seed(app)
    assert client.get("/api/conversations").json()["total"] == 65
    assert len(client.get("/api/conversations/1/messages").json()) == 115
    assert client.get("/api/conversations?channel=voice%20call").json()["total"] == 5
    assert client.get("/api/evaluations?source=ai").json()["total"] == 0
    evaluations = client.get("/api/evaluations?source=test").json()["items"]
    assert [e["initial_score"] for e in evaluations] == ["81.88", "100.00"]
    jobs = client.get("/api/ai/jobs").json()["items"]
    assert [j["status"] for j in jobs] == ["queued", "failed", "cancelled", "failed", "cancelled"]
    assert all(j["evaluation_id"] is None for j in jobs)
    assert client.get("/api/ai/batches/1").json()["percentage"] == "100.00"

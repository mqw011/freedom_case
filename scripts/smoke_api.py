"""Run the Stage 1 acceptance flow through a live HTTP server using synthetic data only.

From backend: uv run python ../scripts/smoke_api.py --base-url http://127.0.0.1:8000/api
"""

import argparse
import copy
import json
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]


def run(base_url: str, *, auth=None, verify=True) -> dict:
    if auth and urlsplit(base_url).scheme != "https":
        raise ValueError("Credentials require HTTPS")
    with httpx.Client(
        base_url=base_url.rstrip("/") + "/",
        timeout=30,
        trust_env=False,
        auth=auth,
        verify=verify,
    ) as client:

        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()

        assert request("GET", "health")["database"] == "ok"
        source = json.loads((ROOT / "examples/synthetic-dataset.json").read_text())
        source["data"]["dataset_group_id"] = f"LOCAL-SMOKE-{uuid4().hex[:8]}"
        files = {"file": ("synthetic.json", json.dumps(source).encode(), "application/json")}
        report = request("POST", "datasets/import-json", files=files)
        assert report["inserted"] == 1
        assert request("POST", "datasets/import-json", files=files)["skipped"] == 1
        conversations = request(
            "GET", "conversations", params={"dataset_id": report["dataset"]["id"]}
        )
        conversation_id = conversations["items"][0]["id"]
        detail = request("GET", f"conversations/{conversation_id}")
        assert detail["messages"][0]["timestamp_raw"] == "00:00"
        assert len(request("GET", f"conversations/{conversation_id}/messages")) == 3
        default = next(
            c for c in request("GET", "checklists")["items"] if c["name"] == "Freedom Broker"
        )
        versions = request("GET", f"checklists/{default['id']}/versions")
        original = next(v for v in versions if v["version_number"] == 1)
        criteria = [
            {k: v for k, v in c.items() if k not in {"id", "checklist_version_id"}}
            for c in original["criteria"]
        ]
        # Keep the user's default checklist and active version untouched by the smoke flow.
        checklist = request(
            "POST",
            "checklists",
            json={
                "name": f"Smoke {source['data']['dataset_group_id']}",
                "description": "Synthetic acceptance scenario",
                "version": {"criteria": criteria},
            },
        )
        payload = json.loads((ROOT / "examples/manual-evaluation.json").read_text())
        payload.update(
            conversation_id=conversation_id,
            checklist_version_id=checklist["active_version_id"],
        )
        payload["results"][0]["evidence"] = [
            {
                "evidence_type": "quote",
                "message_id": detail["messages"][1]["id"],
                "excerpt": "Здравствуйте! Я Анна.",
                "explanation": "Приветствие и представление",
            }
        ]
        evaluation = request("POST", "evaluations", json=payload)
        assert evaluation["initial_score"] == evaluation["final_score"] == "81.88"
        changed = copy.deepcopy(criteria)
        changed[0]["title"] = "Установление контакта: новая формулировка"
        changed[0]["weight"], changed[1]["weight"] = "15", "10"
        version = request(
            "POST", f"checklists/{checklist['id']}/versions", json={"criteria": changed}
        )
        request(
            "POST",
            f"checklists/{checklist['id']}/activate",
            json={"version_id": version["id"]},
        )
        assert request("GET", f"evaluations/{evaluation['id']}") == evaluation
        closing = next(r for r in evaluation["results"] if r["criterion_code"] == "07")
        appeal = request(
            "POST",
            f"evaluations/{evaluation['id']}/appeals",
            json={
                "criterion_result_id": closing["id"],
                "comment": "Учебная апелляция для проверки пересчёта",
            },
        )
        request(
            "POST",
            f"appeals/{appeal['id']}/decision",
            json={
                "decision": "revised",
                "revised_answer": "yes",
                "reason": "Учебное решение проверяющего",
            },
        )
        final = request("GET", f"evaluations/{evaluation['id']}")
        assert final["initial_score"] == "81.88" and final["final_score"] == "88.13"
        return {
            "status": "passed",
            "group_id": source["data"]["dataset_group_id"],
            "conversation_id": conversation_id,
            "evaluation_id": evaluation["id"],
            "initial_score": final["initial_score"],
            "final_score": final["final_score"],
            "new_version_id": version["id"],
            "appeal_id": appeal["id"],
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api")
    parser.add_argument("--credentials-file", type=Path)
    args = parser.parse_args()
    auth = None
    if args.credentials_file:
        if args.credentials_file.stat().st_mode & 0o077:
            parser.error("Credentials file must have mode 0600")
        credentials = json.loads(args.credentials_file.read_text())
        auth = (credentials["username"], credentials["password"])
    print(json.dumps(run(args.base_url, auth=auth), indent=2, ensure_ascii=False))

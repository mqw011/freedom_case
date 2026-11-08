#!/usr/bin/env python3
"""Read-only acceptance of selected real AI jobs over authenticated HTTPS.

The input is a JSON list of {job_id, conversation_id, version_id, label} records.
Only IDs, scores and technical metrics are printed, never transcript/evidence text.
"""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.ai.grounding import validate_grounding  # noqa: E402
from app.schemas.checklists import VersionRead  # noqa: E402
from app.schemas.datasets import ConversationDetail  # noqa: E402
from app.services.ai_contract import EvaluationContext, StructuredEvaluation  # noqa: E402
from app.services.scoring_engine import score  # noqa: E402


def verify(client, jobs):
    def get(path):
        response = client.get(path)
        response.raise_for_status()
        return response.json()

    versions = {}
    offset = 0
    while True:
        page = get(f"checklists?offset={offset}&limit=100")
        for checklist in page["items"]:
            for version in get(f"checklists/{checklist['id']}/versions"):
                versions[version["id"]] = version
        offset += len(page["items"])
        if offset >= page["total"]:
            break
        if not page["items"]:
            raise ValueError("incomplete_catalog")
    rows = []
    for expected in jobs:
        job = get(f"ai/jobs/{expected['job_id']}")
        if job["conversation_id"] != expected["conversation_id"]:
            raise ValueError("wrong_conversation")
        if job["checklist_version_id"] != expected["version_id"]:
            raise ValueError("wrong_pinned_version")
        row = {
            "label": expected["label"],
            "job_id": job["id"],
            "status": job["status"],
            "evaluation_id": job["evaluation_id"],
            "attempts": job["attempts"],
            "error_code": job["error_code"],
            "metrics": {
                key: job["diagnostics"].get(key)
                for key in (
                    "latency_ms",
                    "requests",
                    "repairs",
                    "chunk_count",
                    "input_tokens",
                    "output_tokens",
                    "prompt_version",
                    "needs_human_review",
                    "review_codes",
                )
            },
        }
        if job["status"] != "completed":
            if job["evaluation_id"] is not None:
                raise ValueError("unfinished_job_has_evaluation")
            rows.append(row)
            continue
        evaluation = get(f"evaluations/{job['evaluation_id']}")
        if (
            evaluation["source"] != "ai"
            or evaluation["status"] != "completed"
            or evaluation["conversation_id"] != job["conversation_id"]
            or evaluation["checklist_version_id"] != job["checklist_version_id"]
        ):
            raise ValueError("evaluation_link_mismatch")
        conversation = ConversationDetail.model_validate(
            get(f"conversations/{job['conversation_id']}")
        )
        version = VersionRead.model_validate(versions[job["checklist_version_id"]])
        result = StructuredEvaluation.model_validate(
            {
                "results": [
                    {
                        **{k: r[k] for k in ("criterion_code", "answer", "explanation")},
                        "evidence": [
                            {k: v for k, v in e.items() if k not in {"id", "criterion_result_id"}}
                            for e in r["evidence"]
                        ],
                    }
                    for r in evaluation["results"]
                ]
            }
        )
        validate_grounding(
            EvaluationContext(conversation=conversation, checklist_version=version),
            result,
            {m.id for m in conversation.messages},
        )
        calculated = score(version.criteria, [(r.criterion_code, r.answer) for r in result.results])
        saved = (
            Decimal(evaluation["initial_score"])
            if evaluation["initial_score"] is not None
            else None
        )
        if calculated.final_score != saved:
            raise ValueError("initial_score_mismatch")
        if calculated.critical_violation != evaluation["initial_critical_violation"]:
            raise ValueError("critical_flag_mismatch")
        row.update(
            verified=True,
            initial_score=evaluation["initial_score"],
            final_score=evaluation["final_score"],
            critical_violation=evaluation["critical_violation"],
            message_count=len(conversation.messages),
            na_count=sum(r.answer == "na" for r in result.results),
        )
        rows.append(row)
    return {"all_completed_verified": all(r.get("verified") for r in rows), "jobs": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--credentials-file", type=Path, required=True)
    parser.add_argument("--jobs-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        parsed = urlsplit(args.base_url)
        if parsed.scheme != "https" or parsed.username or parsed.query or parsed.fragment:
            raise ValueError("https_required")
        if args.credentials_file.stat().st_mode & 0o077:
            raise ValueError("private_credentials_required")
        auth = json.loads(args.credentials_file.read_text())
        jobs = json.loads(args.jobs_file.read_text())
        if not isinstance(jobs, list) or not jobs:
            raise ValueError("jobs_required")
        with httpx.Client(
            base_url=args.base_url.rstrip("/") + "/api/",
            auth=(auth["username"], auth["password"]),
            timeout=30,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            report = verify(client, jobs)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["all_completed_verified"] else 1
    except Exception as exc:
        # Validation errors can include private excerpts; print only their category.
        print(json.dumps({"verification_error": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    sys.exit(main())

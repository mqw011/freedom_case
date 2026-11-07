"""API client; never performs inference inside the web request."""

import argparse
import json

import httpx


def main():
    parser = argparse.ArgumentParser(description="CQA AI jobs API client")
    parser.add_argument("--api", default="http://127.0.0.1:8000/api")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("health")
    job = commands.add_parser("evaluate")
    job.add_argument("conversation_id", type=int)
    job.add_argument("--version", type=int)
    job.add_argument("--key")
    batch = commands.add_parser("batch")
    selector = batch.add_mutually_exclusive_group(required=True)
    selector.add_argument("--dataset", type=int)
    selector.add_argument("--ids", type=int, nargs="+")
    selector.add_argument("--language", choices=["RU", "KZ", "EN"])
    batch.add_argument("--version", type=int)
    batch.add_argument("--key")
    for name in ("job", "progress", "retry", "retry-failed", "cancel", "evaluation"):
        commands.add_parser(name).add_argument("id", type=int)
    args = parser.parse_args()
    method = "GET"
    payload = None
    match args.command:
        case "health":
            path = "/ai/health"
        case "evaluate":
            method = "POST"
            path = "/ai/evaluations"
            payload = {
                "conversation_id": args.conversation_id,
                "checklist_version_id": args.version,
                "idempotency_key": args.key,
            }
        case "batch":
            method = "POST"
            path = "/ai/batches"
            payload = {
                "dataset_id": args.dataset,
                "conversation_ids": args.ids,
                "language": args.language,
                "checklist_version_id": args.version,
                "idempotency_key": args.key,
            }
        case "job":
            path = f"/ai/jobs/{args.id}"
        case "progress":
            path = f"/ai/batches/{args.id}"
        case "evaluation":
            path = f"/evaluations/{args.id}"
        case "retry" | "cancel":
            method = "POST"
            path = f"/ai/jobs/{args.id}/{args.command}"
        case "retry-failed":
            method = "POST"
            path = f"/ai/batches/{args.id}/retry-failed"
    try:
        response = httpx.request(
            method, args.api.rstrip("/") + path, json=payload, timeout=30, trust_env=False
        )
    except httpx.HTTPError:
        parser.exit(1, "Backend unavailable\n")
    if not response.is_success:
        parser.exit(1, f"API request rejected: HTTP {response.status_code}\n")
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

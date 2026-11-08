import argparse
import asyncio
import json
import time
from collections import Counter
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from app.ai.benchmark.cases import CASES, make_context
from app.ai.evaluator import LLMEvaluator
from app.ai.exceptions import AIError
from app.ai.jobs import PINNED_SETTINGS
from app.ai.prompt_engine import PROMPT_VERSION
from app.ai.providers import make_provider
from app.core.config import Settings
from app.services.scoring_engine import score


def ratio(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else None


def configuration(settings):
    """Public reproducibility metadata; never serialize the complete Settings object."""
    return {
        "model": settings.llm_model,
        "provider": settings.llm_provider,
        "context_length": settings.llm_context_length,
        "prompt_version": PROMPT_VERSION,
        "inference_settings": {key: getattr(settings, key) for key in PINNED_SETTINGS},
    }


def summarize(rows):
    successful = [r for r in rows if r["status"] == "completed"]
    metrics = [r["metrics"] for r in rows]
    # Audit/chunk requests have different schemas and are excluded from criterion denominators.
    assessments = sum(m["assessment_requests"] for m in metrics)
    return {
        "sample_size": len(rows),
        "completed": len(successful),
        "failed": len(rows) - len(successful),
        "valid_json_rate": ratio(
            sum(m["successful_json"] for m in metrics), sum(m["requests"] for m in metrics)
        ),
        "schema_validation_rate": ratio(sum(m["schema_valid"] for m in metrics), assessments),
        "criterion_completion_rate": ratio(
            sum(m["complete_results"] for m in metrics), assessments
        ),
        "evidence_validity_rate": ratio(
            sum(m["grounded_results"] for m in metrics), sum(m["complete_results"] for m in metrics)
        ),
        "criterion_agreement": ratio(sum(r["matches"] for r in successful), 8 * len(successful)),
        "na_agreement": ratio(sum(r["na_matches"] for r in successful), 4 * len(successful)),
        "score_mae": ratio(sum(r["score_error"] for r in successful), len(successful)),
        "critical_precision": ratio(
            sum(r["tp"] for r in successful), sum(r["tp"] + r["fp"] for r in successful)
        ),
        "critical_recall": ratio(
            sum(r["tp"] for r in successful), sum(r["tp"] + r["fn"] for r in successful)
        ),
        "mean_latency_seconds": ratio(sum(r["latency_seconds"] for r in rows), len(rows)),
        "failures_by_language": dict(
            Counter(r["language"] for r in rows if r["status"] == "failed")
        ),
        "by_language": {
            lang: {
                "cases": sum(r["language"] == lang for r in rows),
                "completed": sum(r["language"] == lang for r in successful),
                "criterion_agreement": ratio(
                    sum(r["matches"] for r in successful if r["language"] == lang),
                    8 * sum(r["language"] == lang for r in successful),
                ),
            }
            for lang in ("RU", "KZ", "EN")
        },
    }


async def run(args):
    settings = Settings()
    rows = []
    for name, language, messages, expected in CASES:
        if args.case and name not in args.case:
            continue
        context = make_context(name, language, messages)
        evaluator = LLMEvaluator(make_provider(settings), settings)
        start = time.monotonic()
        row = {"case": name, "language": language}
        try:
            result = await evaluator.evaluate(context)
            actual = {r.criterion_code: str(r.answer) for r in result.results}
            predicted = score(
                context.checklist_version.criteria,
                [(r.criterion_code, r.answer) for r in result.results],
            )
            reference = score(
                context.checklist_version.criteria,
                [(c, Decimal(v) if v.isdigit() else v) for c, v in expected.items()],
            )
            row.update(
                status="completed",
                matches=sum(actual[c] == v for c, v in expected.items()),
                na_matches=sum(
                    (actual[c] == "na") == (expected[c] == "na") for c in ("02", "03", "04", "07")
                ),
                score_error=float(abs(predicted.final_score - reference.final_score)),
                score=str(predicted.final_score),
                tp=int(actual["08"] == "yes" and expected["08"] == "yes"),
                fp=int(actual["08"] == "yes" and expected["08"] == "no"),
                fn=int(actual["08"] == "no" and expected["08"] == "yes"),
                disagreements=[c for c, v in expected.items() if actual[c] != v],
                # These answers concern only the public synthetic cases in this module.
                answers=actual,
            )
        except AIError as exc:
            row.update(status="failed", error_code=exc.code, rejected_criteria=list(exc.criteria))
        row.update(
            latency_seconds=round(time.monotonic() - start, 2), metrics=asdict(evaluator.metrics)
        )
        rows.append(row)
        report = {
            **configuration(settings),
            "summary": summarize(rows),
            "cases": rows,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(
            json.dumps(
                {"case": name, "status": row["status"], "latency_seconds": row["latency_seconds"]},
                ensure_ascii=False,
            ),
            flush=True,
        )
    print(json.dumps(summarize(rows), ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Real inference on public synthetic reference cases only"
    )
    parser.add_argument("--case", action="append", choices=[c[0] for c in CASES])
    parser.add_argument("--output", type=Path, default=Path("data/ai-verification/benchmark.json"))
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()

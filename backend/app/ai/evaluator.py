import logging
import time

from pydantic import ValidationError

from app.ai.exceptions import AIError, GroundingError, OutputError
from app.ai.grounding import validate_chunk, validate_grounding
from app.ai.output_parser import parse_evaluation
from app.ai.prompt_engine import ChunkReview, PromptEngine, evidence_schema
from app.ai.providers.base import InferenceMetrics, LLMProvider
from app.ai.quality_checks import SemanticReview, repair_feedback, review_prompt, validate_semantic
from app.core.config import Settings
from app.services.ai_contract import EvaluationContext, StructuredEvaluation


class LLMEvaluator:
    """Implements the existing AIEvaluator protocol; never calculates or invents answers."""

    def __init__(self, provider: LLMProvider, settings: Settings):
        self.provider = provider
        self.settings = settings
        self.prompts = PromptEngine(settings)
        self.metrics = InferenceMetrics()

    async def _generate(self, messages, schema):
        if not self.prompts.fits(messages):
            raise AIError("context_limit")
        self.metrics.requests += 1
        try:
            generated = await self.provider.generate_structured(messages, schema)
        except AIError as exc:
            self.metrics.requests += getattr(exc, "requests", 1) - 1
            self.metrics.errors.append(exc.code)
            raise
        self.metrics.requests -= 1
        self.metrics.record(generated)
        return generated.data

    async def _assess(self, context, *, codes=None, transcript=None, facts=None):
        expected = {c.code for c in context.checklist_version.criteria} if codes is None else codes
        repair = None
        feedback = None
        for attempt in range(self.settings.ai_max_repairs + 1):
            messages = self.prompts.build(
                context,
                codes=codes,
                transcript=transcript,
                facts=facts,
                repair=repair,
                review_feedback=feedback,
            )
            try:
                self.metrics.assessment_requests += 1
                data = await self._generate(
                    messages, self.prompts.output_schema(context, codes, messages=transcript)
                )
                output = parse_evaluation(data)
                self.metrics.schema_valid += 1
                actual = [r.criterion_code for r in output.results]
                if set(actual) == expected and len(actual) == len(expected):
                    self.metrics.complete_results += 1
                validate_grounding(
                    context, output, {m.id for m in context.conversation.messages}, codes=codes
                )
                self.metrics.grounded_results += 1
                if self.settings.ai_semantic_review:
                    review_messages = review_prompt(messages, output)
                    review = await self._generate(review_messages, self._review_schema(expected))
                    rejected, warnings = validate_semantic(review, expected)
                    if rejected:
                        feedback = repair_feedback(review, rejected, output)
                        raise GroundingError("semantic_conflict", criteria=tuple(rejected))
                    self.metrics.review_codes.extend(warnings)
                return output
            except (OutputError, GroundingError) as exc:
                logging.getLogger("cqa.inference").info(
                    "assessment_rejected code=%s criteria=%s", exc.code, ",".join(exc.criteria)
                )
                self.metrics.errors.append(exc.code)
                if attempt == self.settings.ai_max_repairs:
                    raise
                self.metrics.repairs += 1
                repair = (
                    f"Previous attempt rejected: {exc.code}. Re-evaluate from evidence, "
                    f"especially criteria {','.join(exc.criteria) or 'all'}. "
                    f"{exc.hint} Return all requested criteria, grounded quotes and bounded ranges."
                )
        raise AssertionError("unreachable")

    @staticmethod
    def _review_schema(codes):
        schema = SemanticReview.model_json_schema()
        schema["properties"]["decisions"].update(minItems=len(codes), maxItems=len(codes))
        schema["$defs"]["SemanticDecision"]["properties"]["criterion_code"]["enum"] = sorted(codes)
        return schema

    async def _review_chunk(self, context, window):
        repair = None
        for attempt in range(self.settings.ai_max_repairs + 1):
            messages = self.prompts.build(
                context, transcript=window, repair=repair, task="chunk_review"
            )
            messages[0]["content"] += """
This is a PARTIAL WINDOW. Do not assign final scores. For EVERY criterion collect observations
and exact evidence in this window, including potential violations. If the required action is not
seen, state only 'not observed in this window', never global absence. covered_message_ids must
list EVERY provided ID exactly once in order. Each fact needs at least one grounded quote or
absence/range bounded by this window. Preserve ambiguity and contrary evidence. Keep observations
short; select the strongest evidence, never discard a possible gross violation.
"""
            try:
                schema = ChunkReview.model_json_schema()
                schema["$defs"]["EvidenceInput"] = evidence_schema(window)
                schema["properties"]["covered_message_ids"].update(
                    minItems=len(window),
                    maxItems=len(window),
                    items={"type": "integer", "enum": [m.id for m in window]},
                )
                codes = [c.code for c in context.checklist_version.criteria]
                schema["properties"]["facts"].update(minItems=len(codes), maxItems=len(codes))
                schema["$defs"]["ChunkCriterionFacts"]["properties"]["criterion_code"]["enum"] = (
                    codes
                )
                data = await self._generate(messages, schema)
                review = ChunkReview.model_validate(data)
                validate_chunk(context, review, {m.id for m in window})
                return review
            except (ValidationError, OutputError, GroundingError) as exc:
                code = exc.code if isinstance(exc, AIError) else "invalid_schema"
                self.metrics.errors.append(code)
                if attempt == self.settings.ai_max_repairs:
                    raise GroundingError(code) from None
                self.metrics.repairs += 1
                repair = (
                    f"Correct rejected chunk review: {code}. "
                    "Include every supplied ID and criterion."
                )
        raise AssertionError("unreachable")

    async def evaluate(self, context: EvaluationContext) -> StructuredEvaluation:
        start = time.monotonic()
        self.metrics = InferenceMetrics()
        # Reserve space for the independent semantic audit and the proposed answers.
        direct = self.prompts.build(context)
        if self.prompts.fits(direct, output_tokens=self.settings.llm_max_output_tokens + 1600):
            result = await self._assess(context)
        else:
            windows = self.prompts.chunks(context)
            self.metrics.chunk_count = len(windows)
            reviews = [await self._review_chunk(context, window) for window in windows]
            covered = {i for review in reviews for i in review.covered_message_ids}
            if covered != {m.id for m in context.conversation.messages}:
                raise GroundingError("coverage_incomplete")
            # Final criterion analysis uses every window's facts, not a lossy generic summary.
            # Partition by criterion when a combined final prompt would exceed context.
            messages = context.conversation.messages
            operators = [m for m in messages if m.speaker == "operator"]
            anchors = {m.id for m in [messages[0], messages[-1], *operators[:1], *operators[-1:]]}
            results = []
            for criterion in context.checklist_version.criteria:
                facts = []
                ids = set(anchors)
                for review in reviews:
                    fact = next(f for f in review.facts if f.criterion_code == criterion.code)
                    facts.append(
                        {"checked_ids": review.covered_message_ids, **fact.model_dump(mode="json")}
                    )
                    for evidence in fact.evidence:
                        ids.update(
                            i
                            for i in (evidence.message_id, evidence.end_message_id)
                            if i is not None
                        )
                selected = [m for m in messages if m.id in ids]
                output = await self._assess(
                    context, codes={criterion.code}, transcript=selected, facts=facts
                )
                results.extend(output.results)
            result = StructuredEvaluation(results=results)
            validate_grounding(context, result, covered)
        self.metrics.latency_ms = int((time.monotonic() - start) * 1000)
        self.metrics.review_codes = sorted(set(self.metrics.review_codes))
        if context.conversation.channel == "voice call":
            self.metrics.review_codes.append("voice_transcript_only")
        return result

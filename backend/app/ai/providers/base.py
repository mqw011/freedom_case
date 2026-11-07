from dataclasses import dataclass, field
from typing import Protocol, TypedDict


class ChatMessage(TypedDict):
    role: str
    content: str


@dataclass
class Generation:
    data: dict
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    requests: int = 1
    response_mode: str = "json_schema"


@dataclass
class InferenceMetrics:
    requests: int = 0
    successful_json: int = 0
    assessment_requests: int = 0
    schema_valid: int = 0
    complete_results: int = 0
    grounded_results: int = 0
    repairs: int = 0
    chunk_count: int = 1
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int = 0
    errors: list[str] = field(default_factory=list)
    review_codes: list[str] = field(default_factory=list)
    response_modes: list[str] = field(default_factory=list)

    def record(self, result: Generation):
        self.requests += result.requests
        self.successful_json += 1
        self.latency_ms += result.latency_ms
        if result.input_tokens is not None:
            self.input_tokens = (self.input_tokens or 0) + result.input_tokens
        if result.output_tokens is not None:
            self.output_tokens = (self.output_tokens or 0) + result.output_tokens
        if result.response_mode not in self.response_modes:
            self.response_modes.append(result.response_mode)


class LLMProvider(Protocol):
    async def generate_structured(
        self, messages: list[ChatMessage], response_schema: dict
    ) -> Generation: ...

    async def health(self) -> dict: ...

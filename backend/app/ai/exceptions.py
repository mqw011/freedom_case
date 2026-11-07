SAFE_MESSAGES = {
    "provider_timeout": "LLM request timed out",
    "provider_connection": "LLM provider is unavailable",
    "provider_rate_limit": "LLM provider rate limit reached",
    "provider_http": "LLM provider returned an HTTP error",
    "model_unavailable": "Configured model is unavailable",
    "provider_configuration": "LLM configuration or response mode is unsupported",
    "remote_disabled": "Remote inference requires explicit deployment opt-in",
    "invalid_json": "LLM returned invalid JSON",
    "invalid_schema": "LLM result failed schema validation",
    "truncated_output": "LLM output or context was truncated",
    "invalid_answers": "LLM criterion answers are incomplete or invalid",
    "invalid_evidence": "LLM evidence is missing or not grounded",
    "semantic_conflict": "LLM evidence does not support the assessment",
    "context_limit": (
        "Complete evidence cannot fit configured context; increase context or review manually"
    ),
    "coverage_incomplete": "Not all transcript messages were reviewed",
    "lease_expired": "Worker lease expired before completion",
    "worker_stopped": "Worker stopped before completion; retry policy applied",
    "worker_error": "Worker failed; inspect safe technical diagnostics",
    "cancelled": "Job was cancelled",
}


class AIError(Exception):
    def __init__(
        self, code: str, *, retryable: bool = False, criteria: tuple[str, ...] = (), hint: str = ""
    ):
        self.code = code
        self.retryable = retryable
        self.criteria = criteria
        self.hint = hint
        self.safe_message = SAFE_MESSAGES[code]
        super().__init__(self.safe_message)


class ProviderError(AIError):
    pass


class OutputError(AIError):
    pass


class GroundingError(AIError):
    pass

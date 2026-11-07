from app.ai.providers.http import HTTPProvider


class OllamaProvider(HTTPProvider):
    """Native Ollama chat: JSON Schema, explicit context and thinking controls."""

    native = True

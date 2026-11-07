from app.ai.providers.ollama import OllamaProvider
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.core.config import Settings


def make_provider(settings: Settings):
    provider = OllamaProvider if settings.llm_provider == "ollama" else OpenAICompatibleProvider
    return provider(settings)

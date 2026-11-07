from app.ai.providers.http import HTTPProvider


class OpenAICompatibleProvider(HTTPProvider):
    """Chat completions transport; context capacity is also configured on the server."""

    native = False

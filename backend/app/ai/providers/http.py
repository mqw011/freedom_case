import asyncio
import ipaddress
import logging
import time
from urllib.parse import urlsplit

import httpx

from app.ai.exceptions import AIError, ProviderError
from app.ai.output_parser import parse_json
from app.ai.providers.base import ChatMessage, Generation
from app.core.config import Settings


def validate_endpoint(settings: Settings):
    if settings.llm_max_output_tokens + 256 >= settings.llm_context_length:
        raise ProviderError("provider_configuration")
    try:
        parsed = urlsplit(settings.llm_base_url)
        _ = parsed.port
    except ValueError:
        raise ProviderError("provider_configuration") from None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ProviderError("provider_configuration")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProviderError("provider_configuration")
    host = parsed.hostname.lower()
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = host == "localhost"
    if not local and not settings.llm_allow_remote:
        raise ProviderError("remote_disabled")


def transport_schema(value):
    """Avoid enormous grammar expansions in llama.cpp; Pydantic enforces lengths later."""
    if isinstance(value, list):
        return [transport_schema(item) for item in value]
    if isinstance(value, dict):
        return {
            key: transport_schema(item)
            for key, item in value.items()
            if key not in {"title", "default", "maxLength"}
            and not (key == "minLength" and item > 1)
            and not (key == "maxItems" and item > 20)
        }
    return value


class HTTPProvider:
    native = False

    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        validate_endpoint(settings)
        self.settings = settings
        self.transport = transport
        self.semaphore = asyncio.Semaphore(settings.llm_max_concurrency)
        base = settings.llm_base_url.rstrip("/")
        self.base_url = base.removesuffix("/v1") if self.native else base
        self.mode = settings.llm_response_mode

    def _payload(self, messages, response_schema, mode):
        settings = self.settings
        if self.native:
            return {
                "model": settings.llm_model,
                "messages": messages,
                "stream": False,
                "think": settings.llm_think,
                "keep_alive": settings.llm_keep_alive,
                "format": response_schema if mode == "json_schema" else "json",
                "options": {
                    "temperature": settings.llm_temperature,
                    "num_ctx": settings.llm_context_length,
                    "num_predict": settings.llm_max_output_tokens,
                    "seed": settings.llm_seed,
                },
            }
        response_format = (
            {"type": "json_object"}
            if mode == "json_object"
            else {
                "type": "json_schema",
                "json_schema": {"name": "cqa_result", "strict": True, "schema": response_schema},
            }
        )
        return {
            "model": settings.llm_model,
            "messages": messages,
            "stream": False,
            "temperature": settings.llm_temperature,
            "max_tokens": settings.llm_max_output_tokens,
            "response_format": response_format,
        }

    def _headers(self):
        key = self.settings.llm_api_key.get_secret_value()
        return {"Authorization": f"Bearer {key}"} if key else {}

    async def generate_structured(
        self, messages: list[ChatMessage], response_schema: dict
    ) -> Generation:
        start = time.monotonic()
        mode = "json_schema" if self.mode == "auto" else self.mode
        requests = 0
        retries = 0
        async with (
            self.semaphore,
            httpx.AsyncClient(
                timeout=httpx.Timeout(self.settings.llm_timeout, connect=10),
                follow_redirects=False,
                trust_env=False,
                transport=self.transport,
            ) as client,
        ):
            while True:
                requests += 1
                try:
                    endpoint = "/api/chat" if self.native else "/chat/completions"
                    response = await client.post(
                        self.base_url + endpoint,
                        json=self._payload(messages, transport_schema(response_schema), mode),
                        headers=self._headers(),
                    )
                    if (
                        response.status_code in {400, 422}
                        and mode == "json_schema"
                        and self.mode == "auto"
                    ):
                        # A single JSON-mode fallback; all application validators still run.
                        mode = "json_object"
                        continue
                    if response.status_code == 404:
                        raise ProviderError("model_unavailable")
                    if response.status_code in {401, 403, 400, 422}:
                        raise ProviderError("provider_configuration")
                    if response.status_code == 429:
                        raise ProviderError("provider_rate_limit", retryable=True)
                    if not response.is_success:
                        raise ProviderError("provider_http", retryable=response.status_code >= 500)
                    try:
                        payload = response.json()
                        if not isinstance(payload, dict):
                            raise ValueError("Invalid envelope")
                        if self.native:
                            if (
                                payload.get("done") is not True
                                or payload.get("done_reason") == "length"
                            ):
                                raise ProviderError("truncated_output")
                            content = payload["message"]["content"]
                            input_tokens = payload.get("prompt_eval_count")
                            output_tokens = payload.get("eval_count")
                        else:
                            choice = payload["choices"][0]
                            if not isinstance(choice, dict):
                                raise ValueError("Invalid choice")
                            if choice.get("finish_reason") != "stop":
                                raise ProviderError("truncated_output")
                            content = choice["message"]["content"]
                            input_tokens = payload.get("usage", {}).get("prompt_tokens")
                            output_tokens = payload.get("usage", {}).get("completion_tokens")
                        if not isinstance(content, str):
                            raise ValueError("Missing content")
                    except (ValueError, KeyError, IndexError, TypeError):
                        raise ProviderError("invalid_json") from None
                    if (
                        self.native
                        and isinstance(input_tokens, int)
                        and (
                            input_tokens
                            >= self.settings.llm_context_length
                            - self.settings.llm_max_output_tokens
                        )
                    ):
                        raise ProviderError("truncated_output")
                    logging.getLogger("cqa.inference").info(
                        "generation_complete duration_ms=%d input_tokens=%s "
                        "output_tokens=%s mode=%s",
                        int((time.monotonic() - start) * 1000),
                        input_tokens,
                        output_tokens,
                        mode,
                    )
                    return Generation(
                        parse_json(content),
                        int((time.monotonic() - start) * 1000),
                        input_tokens,
                        output_tokens,
                        requests,
                        mode,
                    )
                except httpx.TimeoutException:
                    error = ProviderError("provider_timeout", retryable=True)
                except httpx.RequestError:
                    error = ProviderError("provider_connection", retryable=True)
                except AIError as exc:
                    error = exc
                if not error.retryable or retries >= self.settings.llm_max_retries:
                    error.requests = requests
                    raise error from None
                await asyncio.sleep(self.settings.llm_retry_delay * (2**retries))
                retries += 1

    async def health(self) -> dict:
        try:
            async with httpx.AsyncClient(
                timeout=5, trust_env=False, follow_redirects=False, transport=self.transport
            ) as client:
                endpoint = "/api/tags" if self.native else "/models"
                response = await client.get(self.base_url + endpoint, headers=self._headers())
                if response.status_code != 200:
                    raise ValueError("unavailable")
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("Invalid envelope")
                names = (
                    {m.get("name") for m in payload.get("models", [])}
                    if self.native
                    else {m.get("id") for m in payload.get("data", [])}
                )
                available = self.settings.llm_model in names
                return {
                    "available": available,
                    "model": self.settings.llm_model,
                    "error_code": None if available else "model_unavailable",
                }
        except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
            return {
                "available": False,
                "model": self.settings.llm_model,
                "error_code": "provider_connection",
            }

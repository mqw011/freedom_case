import json

import httpx
import pytest

from app.ai.exceptions import AIError
from app.ai.providers.ollama import OllamaProvider
from app.ai.providers.openai_compatible import OpenAICompatibleProvider

MESSAGES = [{"role": "user", "content": "Return JSON"}]
SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


def success(native=True, content='{"ok":true}'):
    return (
        {
            "done": True,
            "done_reason": "stop",
            "message": {"content": content},
            "prompt_eval_count": 10,
            "eval_count": 4,
        }
        if native
        else {
            "choices": [{"finish_reason": "stop", "message": {"content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4},
        }
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "provider,native", [(OllamaProvider, True), (OpenAICompatibleProvider, False)]
)
async def test_structured_response_and_parameters(ai_settings, provider, native):
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=success(native))

    instance = provider(ai_settings, transport=httpx.MockTransport(handler))
    result = await instance.generate_structured(MESSAGES, SCHEMA)
    assert result.data == {"ok": True}
    assert result.input_tokens == 10 and result.output_tokens == 4
    body = captured[0]
    assert body["model"] == ai_settings.llm_model and not body["stream"]
    if native:
        assert body["format"] == SCHEMA and body["think"] is False
        assert body["options"]["num_ctx"] == ai_settings.llm_context_length
    else:
        assert body["response_format"]["json_schema"]["schema"] == SCHEMA


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status,code,attempts",
    [
        (500, "provider_http", 3),
        (429, "provider_rate_limit", 3),
        (404, "model_unavailable", 1),
        (401, "provider_configuration", 1),
        (400, "provider_configuration", 2),
    ],
)
async def test_safe_http_errors(ai_settings, status, code, attempts, caplog):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="private transcript secret-token")

    instance = OllamaProvider(ai_settings, transport=httpx.MockTransport(handler))
    with pytest.raises(AIError) as caught:
        await instance.generate_structured(MESSAGES, SCHEMA)
    assert caught.value.code == code and len(calls) == attempts
    assert "secret-token" not in str(caught.value) + caplog.text
    assert "private transcript" not in str(caught.value) + caplog.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    "exception,code",
    [(httpx.ReadTimeout, "provider_timeout"), (httpx.ConnectError, "provider_connection")],
)
async def test_network_retry_exhaustion(ai_settings, exception, code):
    calls = []

    def handler(request):
        calls.append(1)
        raise exception("sensitive request data")

    instance = OllamaProvider(ai_settings, transport=httpx.MockTransport(handler))
    with pytest.raises(AIError) as caught:
        await instance.generate_structured(MESSAGES, SCHEMA)
    assert caught.value.code == code and len(calls) == 3


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body,code",
    [
        ({}, "truncated_output"),
        ({"done": True}, "invalid_json"),
        (success(content="not JSON"), "invalid_json"),
        (success(content='{"ok":true,"ok":false}'), "invalid_json"),
        (success(content='{"ok":NaN}'), "invalid_json"),
        ({**success(), "done_reason": "length"}, "truncated_output"),
    ],
)
async def test_invalid_outputs(ai_settings, body, code):
    instance = OllamaProvider(
        ai_settings, transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    )
    with pytest.raises(AIError) as caught:
        await instance.generate_structured(MESSAGES, SCHEMA)
    assert caught.value.code == code


@pytest.mark.anyio
async def test_schema_fallback_is_explicit(ai_settings):
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        return (
            httpx.Response(400)
            if isinstance(body["format"], dict)
            else httpx.Response(200, json=success())
        )

    instance = OllamaProvider(ai_settings, transport=httpx.MockTransport(handler))
    result = await instance.generate_structured(MESSAGES, SCHEMA)
    assert len(bodies) == 2 and result.response_mode == "json_object"


@pytest.mark.anyio
async def test_strict_mode_does_not_fallback(ai_settings):
    ai_settings.llm_response_mode = "json_schema"
    instance = OllamaProvider(
        ai_settings, transport=httpx.MockTransport(lambda r: httpx.Response(400))
    )
    with pytest.raises(AIError):
        await instance.generate_structured(MESSAGES, SCHEMA)


@pytest.mark.parametrize(
    "url",
    [
        "https://cloud.example/v1",
        "http://192.168.1.1/v1",
        "file:///tmp/model",
        "http://user:password@localhost/v1",
        "http://localhost/v1?key=secret",
    ],
)
def test_remote_and_invalid_configuration_blocked(ai_settings, url):
    ai_settings.llm_base_url = url
    with pytest.raises(AIError):
        OllamaProvider(ai_settings)


@pytest.mark.anyio
async def test_health_detects_model_without_generating(ai_settings):
    instance = OllamaProvider(
        ai_settings,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"models": [{"name": ai_settings.llm_model}]})
        ),
    )
    assert (await instance.health())["available"]


def test_transport_schema_avoids_large_grammar_without_mutating_contract():
    from app.ai.providers.http import transport_schema
    from app.services.ai_contract import StructuredEvaluation

    original = StructuredEvaluation.model_json_schema()
    simplified = transport_schema(original)
    assert "maxLength" not in str(simplified)
    assert "maxLength" in str(original)
    assert simplified["$defs"]["EvidenceInput"]["additionalProperties"] is False


@pytest.mark.parametrize(
    "url", ["http://[broken", "http://localhost:invalid/v1", "http://localhost:999999/v1"]
)
def test_malformed_endpoints_are_safe_configuration_errors(ai_settings, url):
    ai_settings.llm_base_url = url
    with pytest.raises(AIError) as error:
        OllamaProvider(ai_settings)
    assert error.value.code == "provider_configuration"


@pytest.mark.anyio
@pytest.mark.parametrize("body", [[], None, {"done": True, "message": None}])
async def test_malformed_envelopes(ai_settings, body):
    provider = OllamaProvider(
        ai_settings, transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    )
    with pytest.raises(AIError) as error:
        await provider.generate_structured(MESSAGES, SCHEMA)
    assert error.value.code == "invalid_json"


@pytest.mark.anyio
async def test_context_saturation_is_rejected(ai_settings):
    body = success() | {"prompt_eval_count": ai_settings.llm_context_length - 100}
    provider = OllamaProvider(
        ai_settings, transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    )
    with pytest.raises(AIError) as error:
        await provider.generate_structured(MESSAGES, SCHEMA)
    assert error.value.code == "truncated_output"


@pytest.mark.anyio
async def test_provider_concurrency_limit(ai_settings):
    import asyncio

    active = 0
    maximum = 0

    async def handler(request):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.01)
        active -= 1
        return httpx.Response(200, json=success())

    provider = OllamaProvider(ai_settings, transport=httpx.MockTransport(handler))
    await asyncio.gather(*(provider.generate_structured(MESSAGES, SCHEMA) for _ in range(4)))
    assert maximum == 1


@pytest.mark.anyio
async def test_api_key_is_sent_but_not_logged(ai_settings, caplog):
    from pydantic import SecretStr

    ai_settings.llm_api_key = SecretStr("synthetic-private-key")

    def handler(request):
        assert request.headers["Authorization"] == "Bearer synthetic-private-key"
        return httpx.Response(500, text="synthetic-private-key")

    provider = OpenAICompatibleProvider(ai_settings, transport=httpx.MockTransport(handler))
    with pytest.raises(AIError) as error:
        await provider.generate_structured(MESSAGES, SCHEMA)
    assert "synthetic-private-key" not in caplog.text + str(error.value) + repr(ai_settings)
    assert error.value.requests == 3


def test_output_budget_must_leave_context_room(ai_settings):
    ai_settings.llm_max_output_tokens = ai_settings.llm_context_length
    with pytest.raises(AIError) as error:
        OllamaProvider(ai_settings)
    assert error.value.code == "provider_configuration"

import httpx

from edison_core.schemas import ChatMode, InferenceRequest, ModelCapability, ModelProfile, ModelStatus
from edison_core.services.model_gateway import ModelGateway
from edison_core.services.model_registry import ModelRegistry, ModelRouter


def test_gateway_returns_not_configured_response_for_placeholder_model():
    registry = ModelRegistry(
        [
            ModelProfile(
                id="local-general-chat",
                display_name="Local General Chat",
                provider="local-openai-compatible",
                status=ModelStatus.NOT_CONFIGURED,
                capabilities=[ModelCapability.CHAT],
                endpoint_url="http://127.0.0.1:8002/v1",
            )
        ]
    )

    selection, response = ModelGateway(ModelRouter(registry)).complete(
        InferenceRequest(prompt="Hello", mode=ChatMode.CHAT)
    )

    assert selection.model.id == "local-general-chat"
    assert response.finish_reason == "not_configured"
    assert "not configured" in response.content


def test_gateway_calls_openai_compatible_chat_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        payload = request.read().decode("utf-8")
        assert "Keep it local" in payload
        return httpx.Response(
            200,
            json={
                "id": "cmpl-test",
                "model": "ready-chat",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Local response online."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 4, "completion_tokens": 3},
            },
        )

    registry = ModelRegistry(
        [
            ModelProfile(
                id="ready-chat",
                display_name="Ready Chat",
                provider="local-openai-compatible",
                status=ModelStatus.READY,
                capabilities=[ModelCapability.CHAT],
                endpoint_url="http://model.test/v1",
            )
        ]
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))

    _selection, response = ModelGateway(ModelRouter(registry), http_client=client).complete(
        InferenceRequest(
            prompt="Keep it local",
            mode=ChatMode.CHAT,
            metadata={"messages": [{"role": "user", "content": "Keep it local"}]},
        )
    )

    assert response.model_id == "ready-chat"
    assert response.content == "Local response online."
    assert response.metadata["usage"] == {"prompt_tokens": 4, "completion_tokens": 3}
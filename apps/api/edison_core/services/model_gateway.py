from __future__ import annotations

from typing import Any

import httpx

from edison_core.schemas import InferenceRequest, InferenceResponse, ModelProfile, ModelSelection, ModelStatus
from edison_core.services.model_registry import ModelRouter, ModelSelectionError, capabilities_for_mode


class ModelGateway:
    def __init__(
        self,
        router: ModelRouter,
        timeout_seconds: float = 60.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.router = router
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client

    def complete(self, request: InferenceRequest) -> tuple[ModelSelection, InferenceResponse]:
        try:
            selection = self.router.select_model(
                mode=request.mode,
                preferred_model=request.preferred_model,
            )
        except ModelSelectionError:
            fallback_profile = _fallback_profile(self.router)
            selection = ModelSelection(
                mode=request.mode,
                required_capabilities=capabilities_for_mode(request.mode),
                model=fallback_profile,
                reason="fallback profile used because no model matches required capabilities",
            )
        profile = selection.model

        if profile.status != ModelStatus.READY or not profile.endpoint_url:
            return selection, InferenceResponse(
                model_id=profile.id,
                content=_not_configured_message(profile.display_name),
                finish_reason="not_configured",
                metadata={
                    "provider": profile.provider,
                    "status": profile.status.value,
                    "reason": "selected model is not marked ready or has no endpoint URL",
                },
            )

        if profile.provider != "local-openai-compatible":
            return selection, InferenceResponse(
                model_id=profile.id,
                content=f"The selected model provider '{profile.provider}' is not connected yet.",
                finish_reason="not_configured",
                metadata={"provider": profile.provider, "status": profile.status.value},
            )

        messages = _messages_from_request(request)
        payload = {
            "model": profile.id,
            "messages": messages,
            "stream": False,
            "max_tokens": profile.max_output_tokens,
        }

        try:
            result = self._post(_chat_completions_url(profile.endpoint_url), payload)
            result.raise_for_status()
            body = result.json()
        except httpx.HTTPError as error:
            return selection, InferenceResponse(
                model_id=profile.id,
                content=f"The selected local model endpoint could not complete the request: {error}",
                finish_reason="error",
                metadata={"provider": profile.provider, "status": profile.status.value},
            )

        return selection, _parse_openai_compatible_response(profile.id, body)

    def _post(self, url: str, payload: dict[str, Any]) -> httpx.Response:
        if self.http_client is not None:
            return self.http_client.post(url, json=payload, timeout=self.timeout_seconds)
        with httpx.Client(timeout=self.timeout_seconds) as client:
            return client.post(url, json=payload)


def _messages_from_request(request: InferenceRequest) -> list[dict[str, str]]:
    raw_messages = request.metadata.get("messages")
    if isinstance(raw_messages, list) and raw_messages:
        messages: list[dict[str, str]] = []
        for item in raw_messages:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "user"))
            content = str(item.get("content", ""))
            if content:
                messages.append({"role": role, "content": content})
        if messages:
            return messages
    return [{"role": "user", "content": request.prompt}]


def _chat_completions_url(endpoint_url: str) -> str:
    clean = endpoint_url.rstrip("/")
    if clean.endswith("/chat/completions"):
        return clean
    return f"{clean}/chat/completions"


def _parse_openai_compatible_response(model_id: str, body: dict[str, Any]) -> InferenceResponse:
    choices = body.get("choices") or []
    first_choice = choices[0] if choices else {}
    message = first_choice.get("message") or {}
    content = message.get("content") or ""
    finish_reason = first_choice.get("finish_reason") or "stop"
    normalized_finish_reason = finish_reason if finish_reason in {"stop", "length"} else "stop"
    return InferenceResponse(
        model_id=str(body.get("model") or model_id),
        content=str(content).strip() or "The model returned an empty response.",
        finish_reason=normalized_finish_reason,
        metadata={
            "provider_response_id": body.get("id"),
            "usage": body.get("usage") or {},
            "raw_finish_reason": finish_reason,
        },
    )


def _not_configured_message(model_name: str) -> str:
    return (
        f"{model_name} is selected for this mode, but it is not configured as a ready local model yet. "
        "Start an OpenAI-compatible local model server, mark the profile as ready in the model registry, "
        "and EDISON will route this chat turn through it."
    )


def _fallback_profile(router: ModelRouter) -> ModelProfile:
    profiles = router.registry.list_profiles()
    if profiles:
        return profiles[0]
    return ModelProfile(
        id="local-fallback",
        display_name="Local Fallback",
        provider="local-openai-compatible",
        status=ModelStatus.NOT_CONFIGURED,
        capabilities=[],
        context_window=8192,
        max_output_tokens=1024,
        endpoint_url=None,
    )
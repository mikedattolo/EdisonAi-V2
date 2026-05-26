from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from edison_core.schemas import ChatMode, InferenceRequest, InferenceResponse, ModelProfile, ModelSelection, ModelStatus
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
        selection = self._select_model(request)
        profile = selection.model

        unavailable = _unavailable_response(profile)
        if unavailable is not None:
            return selection, unavailable

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

    def stream_complete(self, request: InferenceRequest) -> tuple[ModelSelection, "InferenceStream"]:
        selection = self._select_model(request)
        profile = selection.model
        return selection, InferenceStream(self, profile, request)

    def _select_model(self, request: InferenceRequest) -> ModelSelection:
        try:
            return self.router.select_model(
                mode=request.mode,
                preferred_model=request.preferred_model,
            )
        except ModelSelectionError:
            fallback_profile = _fallback_profile(self.router)
            return ModelSelection(
                mode=request.mode,
                required_capabilities=capabilities_for_mode(request.mode),
                model=fallback_profile,
                reason="fallback profile used because no model matches required capabilities",
            )

    def _post(self, url: str, payload: dict[str, Any]) -> httpx.Response:
        if self.http_client is not None:
            return self.http_client.post(url, json=payload, timeout=self.timeout_seconds)
        with httpx.Client(timeout=self.timeout_seconds) as client:
            return client.post(url, json=payload)


@dataclass
class InferenceStreamEvent:
    event: str
    token: str = ""
    inference: InferenceResponse | None = None


class InferenceStream:
    def __init__(self, gateway: ModelGateway, profile: ModelProfile, request: InferenceRequest) -> None:
        self.gateway = gateway
        self.profile = profile
        self.request = request

    def __iter__(self):
        unavailable = _unavailable_response(self.profile)
        if unavailable is not None:
            yield InferenceStreamEvent(event="token", token=unavailable.content)
            yield InferenceStreamEvent(event="done", inference=unavailable)
            return

        if self.profile.provider != "local-openai-compatible":
            response = InferenceResponse(
                model_id=self.profile.id,
                content=f"The selected model provider '{self.profile.provider}' is not connected yet.",
                finish_reason="not_configured",
                metadata={"provider": self.profile.provider, "status": self.profile.status.value},
            )
            yield InferenceStreamEvent(event="token", token=response.content)
            yield InferenceStreamEvent(event="done", inference=response)
            return

        messages = _messages_from_request(self.request)
        payload = {
            "model": self.profile.id,
            "messages": messages,
            "stream": True,
            "max_tokens": self.profile.max_output_tokens,
        }
        content_parts: list[str] = []
        finish_reason = "stop"
        response_id: str | None = None
        trace_filter = ReasoningTraceFilter()

        try:
            for chunk in self._stream_openai_chunks(_chat_completions_url(self.profile.endpoint_url or ""), payload):
                response_id = response_id or str(chunk.get("id") or "")
                choices = chunk.get("choices") or []
                first_choice = choices[0] if choices else {}
                delta = first_choice.get("delta") or {}
                token = delta.get("content") or first_choice.get("text") or ""
                if token:
                    visible_token = trace_filter.feed(str(token))
                    if visible_token:
                        content_parts.append(visible_token)
                        yield InferenceStreamEvent(event="token", token=visible_token)
                finish_reason = first_choice.get("finish_reason") or finish_reason
        except httpx.HTTPError as error:
            response = InferenceResponse(
                model_id=self.profile.id,
                content=f"The selected local model endpoint could not complete the request: {error}",
                finish_reason="error",
                metadata={"provider": self.profile.provider, "status": self.profile.status.value},
            )
            yield InferenceStreamEvent(event="done", inference=response)
            return

        final_visible_token = trace_filter.flush()
        if final_visible_token:
            content_parts.append(final_visible_token)
            yield InferenceStreamEvent(event="token", token=final_visible_token)

        normalized_finish_reason = finish_reason if finish_reason in {"stop", "length"} else "stop"
        response = InferenceResponse(
            model_id=self.profile.id,
            content="".join(content_parts).strip() or "The model returned an empty response.",
            finish_reason=normalized_finish_reason,
            metadata={
                "provider_response_id": response_id or None,
                "usage": {},
                "raw_finish_reason": finish_reason,
                "streamed": True,
            },
        )
        yield InferenceStreamEvent(event="done", inference=response)

    def _stream_openai_chunks(self, url: str, payload: dict[str, Any]):
        if self.gateway.http_client is not None:
            with self.gateway.http_client.stream("POST", url, json=payload, timeout=self.gateway.timeout_seconds) as response:
                response.raise_for_status()
                yield from _iter_sse_json(response)
            return
        with httpx.Client(timeout=self.gateway.timeout_seconds) as client:
            with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                yield from _iter_sse_json(response)


def _iter_sse_json(response: httpx.Response):
    for line in response.iter_lines():
        if not line:
            continue
        data = line[6:].strip() if line.startswith("data: ") else line.strip()
        if data == "[DONE]":
            break
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            yield payload


def _unavailable_response(profile: ModelProfile) -> InferenceResponse | None:
    if profile.status != ModelStatus.READY or not profile.endpoint_url:
        return InferenceResponse(
            model_id=profile.id,
            content=_not_configured_message(profile.display_name),
            finish_reason="not_configured",
            metadata={
                "provider": profile.provider,
                "status": profile.status.value,
                "reason": "selected model is not marked ready or has no endpoint URL",
            },
        )
    return None


def _messages_from_request(request: InferenceRequest) -> list[dict[str, str]]:
    raw_messages = request.metadata.get("messages")
    system_prompt = _assistant_system_prompt(request.mode)
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
            return [{"role": "system", "content": system_prompt}, *messages]
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": request.prompt}]


def _chat_completions_url(endpoint_url: str) -> str:
    clean = endpoint_url.rstrip("/")
    if clean.endswith("/chat/completions"):
        return clean
    return f"{clean}/chat/completions"


def _parse_openai_compatible_response(model_id: str, body: dict[str, Any]) -> InferenceResponse:
    choices = body.get("choices") or []
    first_choice = choices[0] if choices else {}
    message = first_choice.get("message") or {}
    content = _clean_model_content(str(message.get("content") or ""))
    finish_reason = first_choice.get("finish_reason") or "stop"
    normalized_finish_reason = finish_reason if finish_reason in {"stop", "length"} else "stop"
    return InferenceResponse(
        model_id=str(body.get("model") or model_id),
        content=content.strip() or "The model returned an empty response.",
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


class ReasoningTraceFilter:
    """Suppress model-private <think> traces while preserving streamed answer text."""

    def __init__(self) -> None:
        self.buffer = ""
        self.suppressing = False

    def feed(self, text: str) -> str:
        self.buffer += text
        visible_parts: list[str] = []
        while self.buffer:
            lowered = self.buffer.lower()
            if self.suppressing:
                close_index = lowered.find("</think>")
                if close_index < 0:
                    self.buffer = self.buffer[-16:] if len(self.buffer) > 16 else self.buffer
                    break
                self.buffer = self.buffer[close_index + len("</think>") :]
                self.suppressing = False
                if self.buffer.startswith("\n\n"):
                    self.buffer = self.buffer.lstrip()
                continue

            open_index = lowered.find("<think")
            if open_index < 0:
                emit_length = max(0, len(self.buffer) - len("<think"))
                if emit_length == 0:
                    break
                visible_parts.append(self.buffer[:emit_length])
                self.buffer = self.buffer[emit_length:]
                break

            visible_parts.append(self.buffer[:open_index])
            close_tag = self.buffer.find(">", open_index)
            self.buffer = "" if close_tag < 0 else self.buffer[close_tag + 1 :]
            self.suppressing = True

        return "".join(visible_parts)

    def flush(self) -> str:
        if self.suppressing:
            self.buffer = ""
            return ""
        remaining = self.buffer
        self.buffer = ""
        return remaining


def _clean_model_content(content: str) -> str:
    filter_ = ReasoningTraceFilter()
    return (filter_.feed(content) + filter_.flush()).strip()


def _assistant_system_prompt(mode: ChatMode) -> str:
    mode_guidance = {
        ChatMode.CODING: "For coding work, cite concrete files and verification steps. Keep diffs and commands scoped.",
        ChatMode.REASONING: "For harder problems, think carefully internally and present the useful reasoning summary, not hidden scratch work.",
        ChatMode.CREATIVE: "For creative work, offer vivid options and make the result easy to act on.",
        ChatMode.MEDIA: "For media work, explain what will be generated, what input is required, and where the result will appear.",
        ChatMode.AGENT: "For agentic work, be clear about status, next actions, and any side effects.",
        ChatMode.SWARM: "For parallel work, summarize lanes and outcomes without dumping coordination internals.",
        ChatMode.INSTANT: "For quick mode, answer directly in a few sentences.",
        ChatMode.CHAT: "For normal chat, be helpful, conversational, and concise.",
    }
    return (
        "You are Edison, a polished local AI assistant running on Mike's AI PC. "
        "Answer like a modern ChatGPT or Claude-style assistant: clear, friendly, useful, and structured only when structure helps. "
        "Do not expose hidden chain-of-thought, internal scratchpads, raw model tags, or low-level routing details. "
        "Use concise Markdown for lists, code, and steps. If a request is ambiguous, ask one brief clarifying question or make a safe assumption and say it. "
        f"{mode_guidance.get(mode, mode_guidance[ChatMode.CHAT])}"
    )

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from edison_core.schemas import ChatMode, ModelCapability, ModelProfile, ModelSelection, ModelStatus


class ModelSelectionError(ValueError):
    pass


class ModelRegistry:
    def __init__(self, profiles: Iterable[ModelProfile] = ()) -> None:
        self._profiles = {profile.id: profile for profile in profiles}

    @classmethod
    def from_file(cls, path: str | Path) -> "ModelRegistry":
        registry_path = Path(path)
        if not registry_path.exists():
            return cls(default_profiles())
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
        return cls(ModelProfile(**item) for item in payload.get("models", []))

    def list_profiles(self) -> list[ModelProfile]:
        return sorted(self._profiles.values(), key=lambda profile: profile.id)

    def get(self, model_id: str) -> ModelProfile | None:
        return self._profiles.get(model_id)

    def find_by_capabilities(self, capabilities: Iterable[ModelCapability]) -> list[ModelProfile]:
        required = set(capabilities)
        return [
            profile
            for profile in self.list_profiles()
            if required.issubset(set(profile.capabilities))
        ]


class ModelRouter:
    def __init__(self, registry: ModelRegistry) -> None:
        self.registry = registry

    def select_model(
        self,
        mode: ChatMode,
        required_capabilities: Iterable[ModelCapability] | None = None,
        preferred_model: str | None = None,
    ) -> ModelSelection:
        required = list(required_capabilities or capabilities_for_mode(mode))
        if preferred_model:
            profile = self.registry.get(preferred_model)
            if profile and set(required).issubset(set(profile.capabilities)):
                return ModelSelection(
                    mode=mode,
                    required_capabilities=required,
                    model=profile,
                    reason="preferred model satisfies requested capabilities",
                )

        candidates = self.registry.find_by_capabilities(required)
        if not candidates:
            raise ModelSelectionError(f"No model profile supports {[cap.value for cap in required]}")

        candidates.sort(key=lambda profile: _selection_sort_key(profile, mode))
        return ModelSelection(
            mode=mode,
            required_capabilities=required,
            model=candidates[0],
            reason="best profile by status, context window, and output size",
        )


def capabilities_for_mode(mode: ChatMode) -> list[ModelCapability]:
    mapping = {
        ChatMode.AUTO: [ModelCapability.CHAT],
        ChatMode.INSTANT: [ModelCapability.CHAT, ModelCapability.FAST_CHAT],
        ChatMode.CHAT: [ModelCapability.CHAT],
        ChatMode.REASONING: [ModelCapability.CHAT, ModelCapability.REASONING],
        ChatMode.CODING: [ModelCapability.CHAT, ModelCapability.CODING],
        ChatMode.AGENT: [ModelCapability.CHAT, ModelCapability.TOOL_CALLING],
        ChatMode.SWARM: [ModelCapability.CHAT, ModelCapability.TOOL_CALLING],
        ChatMode.CREATIVE: [ModelCapability.CHAT],
        ChatMode.MEDIA: [ModelCapability.MEDIA],
    }
    return mapping[mode]


def default_profiles() -> list[ModelProfile]:
    return [
        ModelProfile(
            id="local-general-chat",
            display_name="Local General Chat",
            provider="local-openai-compatible",
            status=ModelStatus.NOT_CONFIGURED,
            capabilities=[ModelCapability.CHAT, ModelCapability.LONG_CONTEXT, ModelCapability.TOOL_CALLING],
            license="See model card",
            tags=["general", "assistant", "local"],
            safety_notes="Verify important claims with sources and require approval for side effects.",
            context_window=32768,
            max_output_tokens=4096,
            endpoint_url="http://127.0.0.1:8002/v1",
            preferred_gpu="RTX 3090",
        )
    ]


def _selection_sort_key(profile: ModelProfile, mode: ChatMode) -> tuple[int, int, int, int, str]:
    status_rank = {
        ModelStatus.READY: 0,
        ModelStatus.DEGRADED: 1,
        ModelStatus.NOT_CONFIGURED: 2,
        ModelStatus.OFFLINE: 3,
    }
    return (
        status_rank.get(profile.status, 9),
        _mode_specialization_penalty(profile, mode),
        -profile.context_window,
        -profile.max_output_tokens,
        profile.id,
    )


def _mode_specialization_penalty(profile: ModelProfile, mode: ChatMode) -> int:
    if mode not in {ChatMode.AUTO, ChatMode.CHAT}:
        return 0
    specialist_capabilities = {
        ModelCapability.REASONING,
        ModelCapability.CODING,
        ModelCapability.VISION,
        ModelCapability.MEDIA,
        ModelCapability.EMBEDDINGS,
        ModelCapability.RERANKING,
    }
    return len(set(profile.capabilities).intersection(specialist_capabilities))

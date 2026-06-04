import pytest

from edison_core.schemas import ChatMode, ModelCapability, ModelProfile, ModelStatus
from edison_core.services.model_registry import ModelRegistry, ModelRouter, ModelSelectionError


def test_router_prefers_ready_model_with_required_capabilities():
    registry = ModelRegistry(
        [
            ModelProfile(
                id="slow-not-configured",
                display_name="Slow Placeholder",
                provider="local",
                status=ModelStatus.NOT_CONFIGURED,
                capabilities=[ModelCapability.CHAT, ModelCapability.CODING],
                context_window=65536,
            ),
            ModelProfile(
                id="ready-coder",
                display_name="Ready Coder",
                provider="local",
                status=ModelStatus.READY,
                capabilities=[ModelCapability.CHAT, ModelCapability.CODING],
                context_window=32768,
            ),
        ]
    )

    selection = ModelRouter(registry).select_model(ChatMode.CODING)

    assert selection.model.id == "ready-coder"
    assert ModelCapability.CODING in selection.required_capabilities


def test_chat_mode_prefers_general_profile_over_specialist_profile():
    registry = ModelRegistry(
        [
            ModelProfile(
                id="general-chat",
                display_name="General Chat",
                provider="local",
                status=ModelStatus.NOT_CONFIGURED,
                capabilities=[ModelCapability.CHAT, ModelCapability.LONG_CONTEXT],
                context_window=32768,
                max_output_tokens=4096,
            ),
            ModelProfile(
                id="reasoning-chat",
                display_name="Reasoning Chat",
                provider="local",
                status=ModelStatus.NOT_CONFIGURED,
                capabilities=[ModelCapability.CHAT, ModelCapability.REASONING, ModelCapability.LONG_CONTEXT],
                context_window=32768,
                max_output_tokens=8192,
            ),
        ]
    )

    selection = ModelRouter(registry).select_model(ChatMode.CHAT)

    assert selection.model.id == "general-chat"


def test_auto_mode_uses_general_chat_capabilities():
    registry = ModelRegistry(
        [
            ModelProfile(
                id="general-chat",
                display_name="General Chat",
                provider="local",
                status=ModelStatus.READY,
                capabilities=[ModelCapability.CHAT],
            )
        ]
    )

    selection = ModelRouter(registry).select_model(ChatMode.AUTO)

    assert selection.mode == ChatMode.AUTO
    assert selection.required_capabilities == [ModelCapability.CHAT]
    assert selection.model.id == "general-chat"


def test_router_raises_when_no_profile_supports_mode():
    registry = ModelRegistry(
        [
            ModelProfile(
                id="chat-only",
                display_name="Chat Only",
                provider="local",
                status=ModelStatus.READY,
                capabilities=[ModelCapability.CHAT],
            )
        ]
    )

    with pytest.raises(ModelSelectionError):
        ModelRouter(registry).select_model(ChatMode.MEDIA)


def test_model_profile_supports_governance_metadata_fields():
    profile = ModelProfile(
        id="governed-profile",
        display_name="Governed Profile",
        provider="local-openai-compatible",
        status=ModelStatus.NOT_CONFIGURED,
        capabilities=[ModelCapability.CHAT],
        license="Apache-2.0",
        tags=["local", "chat"],
        safety_notes="Human verification required for destructive tool suggestions.",
    )

    assert profile.license == "Apache-2.0"
    assert profile.tags == ["local", "chat"]
    assert "verification" in profile.safety_notes.lower()

from __future__ import annotations

import json
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from edison_core.api.dependencies import (
    get_agent_run_store,
    get_conversation_store,
    get_generation_store,
    get_hardware_device_service,
    get_knowledge_store,
    get_model_gateway,
    get_personal_workspace_store,
    get_workspace_tools,
)
from edison_core.api.routes_hardware import _release_camera_feeds, _save_camera_artifact
from edison_core.schemas import (
    AgentRunCreate,
    AgentRunEventCreate,
    AgentRunEventKind,
    AgentRunStatus,
    AgentRunStatusUpdate,
    AgentRunWithEvents,
    ArtifactRecord,
    CameraSnapshotRequest,
    ChatMode,
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    InferenceRequest,
    InferenceResponse,
    MessageCreate,
    MessageRole,
    ModelProfile,
    ModelSelection,
    ModelStatus,
    OrganizerStatus,
    WorkspaceIndexSearchRequest,
)
from edison_core.services.agent_run_store import AgentRunStore
from edison_core.services.conversation_store import ConversationNotFoundError, ConversationStore
from edison_core.services.generation_store import GenerationStore
from edison_core.services.hardware_devices import CameraCaptureError, HardwareDeviceService
from edison_core.services.knowledge_store import KnowledgeStore
from edison_core.services.model_gateway import ModelGateway
from edison_core.services.personal_workspace import PersonalWorkspaceStore
from edison_core.services.workspace_tools import WorkspaceNotFoundError, WorkspaceTools


router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
def create_chat_turn(
    payload: ChatRequest,
    conversations: ConversationStore = Depends(get_conversation_store),
    gateway: ModelGateway = Depends(get_model_gateway),
    workspace: WorkspaceTools = Depends(get_workspace_tools),
    hardware: HardwareDeviceService = Depends(get_hardware_device_service),
    generation_store: GenerationStore = Depends(get_generation_store),
    knowledge: KnowledgeStore = Depends(get_knowledge_store),
    personal: PersonalWorkspaceStore = Depends(get_personal_workspace_store),
    agent_runs: AgentRunStore = Depends(get_agent_run_store),
) -> ChatResponse:
    resolved_payload, intent_metadata = _resolve_chat_payload(payload)
    try:
        conversation_id = _ensure_conversation(resolved_payload, conversations)
        workspace_messages, workspace_metadata = _build_workspace_context(resolved_payload, workspace)
        knowledge_messages, knowledge_metadata = _build_knowledge_context(resolved_payload, knowledge)
        personal_messages, personal_metadata = _build_personal_context(resolved_payload, personal)
        context_messages = workspace_messages + knowledge_messages + personal_messages
        agent_run = _create_agent_run_if_needed(
            resolved_payload,
            payload,
            conversation_id,
            intent_metadata,
            agent_runs,
        )
        _record_agent_context_event(agent_run, agent_runs, workspace_metadata, knowledge_metadata, personal_metadata)
        user_message = conversations.add_message(
            conversation_id,
            MessageCreate(
                role=MessageRole.USER,
                content=resolved_payload.message,
                model=resolved_payload.preferred_model,
                metadata={
                    "mode": resolved_payload.mode.value,
                    "requested_mode": payload.mode.value,
                    "agent_enabled": payload.agent_enabled,
                    "intent_router": intent_metadata,
                    "workspace_path": resolved_payload.workspace_path,
                    "workspace_context_paths": resolved_payload.workspace_context_paths,
                    "context_warnings": (
                        workspace_metadata["warnings"]
                        + knowledge_metadata["warnings"]
                        + personal_metadata["warnings"]
                    ),
                    "agent_run_id": agent_run.id if agent_run else None,
                },
            ),
        )
        conversation = conversations.get_conversation(conversation_id)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found") from error

    if _is_camera_chat_request(resolved_payload.message):
        camera_result = _run_camera_chat_action(resolved_payload, hardware, generation_store, gateway)
        _complete_agent_run_if_needed(agent_run, agent_runs, camera_result.inference.finish_reason)
        assistant_message = conversations.add_message(
            conversation_id,
            MessageCreate(
                role=MessageRole.ASSISTANT,
                content=camera_result.inference.content,
                model=camera_result.inference.model_id,
                metadata={
                    "finish_reason": camera_result.inference.finish_reason,
                    "gateway": camera_result.inference.metadata,
                    "model_selection_reason": camera_result.model_selection.reason,
                    "requested_mode": payload.mode.value,
                    "resolved_mode": resolved_payload.mode.value,
                    "agent_enabled": payload.agent_enabled,
                    "intent_router": {**intent_metadata, "tool_action": "camera.analyze_frame"},
                    "workspace_context": workspace_metadata,
                    "knowledge_context": knowledge_metadata,
                    "personal_context": personal_metadata,
                    "agent_run_id": agent_run.id if agent_run else None,
                    "camera_action": camera_result.metadata,
                },
            ),
        )
        return ChatResponse(
            conversation=conversations.get_conversation(conversation_id),
            user_message=user_message,
            assistant_message=assistant_message,
            inference=camera_result.inference,
            model_selection=camera_result.model_selection,
        )

    model_messages = context_messages + _openai_messages(conversation.messages)
    model_selection, inference = gateway.complete(
        InferenceRequest(
            prompt=resolved_payload.message,
            mode=resolved_payload.mode,
            preferred_model=resolved_payload.preferred_model,
            metadata={
                "conversation_id": conversation_id,
                "messages": model_messages,
                "intent_router": intent_metadata,
                "workspace_context": workspace_metadata,
                "knowledge_context": knowledge_metadata,
                "personal_context": personal_metadata,
                "agent_run_id": agent_run.id if agent_run else None,
            },
        )
    )
    _complete_agent_run_if_needed(agent_run, agent_runs, inference.finish_reason)
    assistant_message = conversations.add_message(
        conversation_id,
        MessageCreate(
            role=MessageRole.ASSISTANT,
            content=inference.content,
            model=inference.model_id,
            metadata={
                "finish_reason": inference.finish_reason,
                "gateway": inference.metadata,
                "model_selection_reason": model_selection.reason,
                "requested_mode": payload.mode.value,
                "resolved_mode": resolved_payload.mode.value,
                "agent_enabled": payload.agent_enabled,
                "intent_router": intent_metadata,
                "workspace_context": workspace_metadata,
                "knowledge_context": knowledge_metadata,
                "personal_context": personal_metadata,
                "agent_run_id": agent_run.id if agent_run else None,
            },
        ),
    )
    return ChatResponse(
        conversation=conversations.get_conversation(conversation_id),
        user_message=user_message,
        assistant_message=assistant_message,
        inference=inference,
        model_selection=model_selection,
    )


@router.post("/stream")
def stream_chat_turn(
    payload: ChatRequest,
    conversations: ConversationStore = Depends(get_conversation_store),
    gateway: ModelGateway = Depends(get_model_gateway),
    workspace: WorkspaceTools = Depends(get_workspace_tools),
    hardware: HardwareDeviceService = Depends(get_hardware_device_service),
    generation_store: GenerationStore = Depends(get_generation_store),
    knowledge: KnowledgeStore = Depends(get_knowledge_store),
    personal: PersonalWorkspaceStore = Depends(get_personal_workspace_store),
    agent_runs: AgentRunStore = Depends(get_agent_run_store),
) -> StreamingResponse:
    resolved_payload, intent_metadata = _resolve_chat_payload(payload)
    try:
        conversation_id = _ensure_conversation(resolved_payload, conversations)
        workspace_messages, workspace_metadata = _build_workspace_context(resolved_payload, workspace)
        knowledge_messages, knowledge_metadata = _build_knowledge_context(resolved_payload, knowledge)
        personal_messages, personal_metadata = _build_personal_context(resolved_payload, personal)
        context_messages = workspace_messages + knowledge_messages + personal_messages
        agent_run = _create_agent_run_if_needed(
            resolved_payload,
            payload,
            conversation_id,
            intent_metadata,
            agent_runs,
        )
        _record_agent_context_event(agent_run, agent_runs, workspace_metadata, knowledge_metadata, personal_metadata)
        user_message = conversations.add_message(
            conversation_id,
            MessageCreate(
                role=MessageRole.USER,
                content=resolved_payload.message,
                model=resolved_payload.preferred_model,
                metadata={
                    "mode": resolved_payload.mode.value,
                    "requested_mode": payload.mode.value,
                    "agent_enabled": payload.agent_enabled,
                    "intent_router": intent_metadata,
                    "workspace_path": resolved_payload.workspace_path,
                    "workspace_context_paths": resolved_payload.workspace_context_paths,
                    "context_warnings": (
                        workspace_metadata["warnings"]
                        + knowledge_metadata["warnings"]
                        + personal_metadata["warnings"]
                    ),
                    "streamed": True,
                    "agent_run_id": agent_run.id if agent_run else None,
                },
            ),
        )
        conversation = conversations.get_conversation(conversation_id)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found") from error

    if _is_camera_chat_request(resolved_payload.message):
        camera_result = _run_camera_chat_action(resolved_payload, hardware, generation_store, gateway)

        def camera_event_source():
            yield _sse(
                "start",
                {
                    "conversation_id": conversation_id,
                    "user_message": user_message.model_dump(mode="json"),
                    "model_selection": camera_result.model_selection.model_dump(mode="json"),
                    "agent_run": agent_run.model_dump(mode="json") if agent_run else None,
                },
            )
            yield _sse("token", {"delta": camera_result.inference.content})
            _complete_agent_run_if_needed(agent_run, agent_runs, camera_result.inference.finish_reason)
            assistant_message = conversations.add_message(
                conversation_id,
                MessageCreate(
                    role=MessageRole.ASSISTANT,
                    content=camera_result.inference.content,
                    model=camera_result.inference.model_id,
                    metadata={
                        "finish_reason": camera_result.inference.finish_reason,
                        "gateway": camera_result.inference.metadata,
                        "model_selection_reason": camera_result.model_selection.reason,
                        "requested_mode": payload.mode.value,
                        "resolved_mode": resolved_payload.mode.value,
                        "agent_enabled": payload.agent_enabled,
                        "intent_router": {**intent_metadata, "tool_action": "camera.analyze_frame"},
                        "workspace_context": workspace_metadata,
                        "knowledge_context": knowledge_metadata,
                        "personal_context": personal_metadata,
                        "streamed": True,
                        "agent_run_id": agent_run.id if agent_run else None,
                        "camera_action": camera_result.metadata,
                    },
                ),
            )
            response = ChatResponse(
                conversation=conversations.get_conversation(conversation_id),
                user_message=user_message,
                assistant_message=assistant_message,
                inference=camera_result.inference,
                model_selection=camera_result.model_selection,
            )
            yield _sse("done", response.model_dump(mode="json"))

        return StreamingResponse(
            camera_event_source(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    model_messages = context_messages + _openai_messages(conversation.messages)
    selection, stream = gateway.stream_complete(
        InferenceRequest(
            prompt=resolved_payload.message,
            mode=resolved_payload.mode,
            preferred_model=resolved_payload.preferred_model,
            metadata={
                "conversation_id": conversation_id,
                "messages": model_messages,
                "intent_router": intent_metadata,
                "workspace_context": workspace_metadata,
                "knowledge_context": knowledge_metadata,
                "personal_context": personal_metadata,
                "agent_run_id": agent_run.id if agent_run else None,
            },
        )
    )

    def event_source():
        yield _sse(
            "start",
            {
                "conversation_id": conversation_id,
                "user_message": user_message.model_dump(mode="json"),
                "model_selection": selection.model_dump(mode="json"),
                "agent_run": agent_run.model_dump(mode="json") if agent_run else None,
            },
        )
        final_inference = None
        for event in stream:
            if event.event == "token":
                yield _sse("token", {"delta": event.token})
                continue
            if event.event == "done" and event.inference is not None:
                final_inference = event.inference
                break

        if final_inference is None:
            _fail_agent_run_if_needed(agent_run, agent_runs, "Chat stream ended without a final response.")
            yield _sse("error", {"detail": "Chat stream ended without a final response."})
            return

        _complete_agent_run_if_needed(agent_run, agent_runs, final_inference.finish_reason)
        assistant_message = conversations.add_message(
            conversation_id,
            MessageCreate(
                role=MessageRole.ASSISTANT,
                content=final_inference.content,
                model=final_inference.model_id,
                metadata={
                    "finish_reason": final_inference.finish_reason,
                    "gateway": final_inference.metadata,
                    "model_selection_reason": selection.reason,
                    "requested_mode": payload.mode.value,
                    "resolved_mode": resolved_payload.mode.value,
                    "agent_enabled": payload.agent_enabled,
                    "intent_router": intent_metadata,
                    "workspace_context": workspace_metadata,
                    "knowledge_context": knowledge_metadata,
                    "personal_context": personal_metadata,
                    "streamed": True,
                    "agent_run_id": agent_run.id if agent_run else None,
                },
            ),
        )
        response = ChatResponse(
            conversation=conversations.get_conversation(conversation_id),
            user_message=user_message,
            assistant_message=assistant_message,
            inference=final_inference,
            model_selection=selection,
        )
        yield _sse("done", response.model_dump(mode="json"))

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _create_agent_run_if_needed(
    resolved_payload: ChatRequest,
    original_payload: ChatRequest,
    conversation_id: str,
    intent_metadata: dict,
    agent_runs: AgentRunStore,
) -> AgentRunWithEvents | None:
    if resolved_payload.mode != ChatMode.AGENT:
        return None
    return agent_runs.create_run(
        AgentRunCreate(
            title=_title_from_message(resolved_payload.message),
            prompt=resolved_payload.message,
            mode=resolved_payload.mode,
            conversation_id=conversation_id,
            metadata={
                "requested_mode": original_payload.mode.value,
                "agent_enabled": original_payload.agent_enabled,
                "intent_router": intent_metadata,
                "source": "chat",
            },
        )
    )


def _record_agent_context_event(
    agent_run: AgentRunWithEvents | None,
    agent_runs: AgentRunStore,
    workspace_metadata: dict,
    knowledge_metadata: dict,
    personal_metadata: dict,
) -> None:
    if agent_run is None:
        return
    warnings = (
        workspace_metadata.get("warnings", [])
        + knowledge_metadata.get("warnings", [])
        + personal_metadata.get("warnings", [])
    )
    agent_runs.add_event(
        agent_run.id,
        AgentRunEventCreate(
            kind=AgentRunEventKind.TOOL_RESULT,
            title="Context assembled",
            body=(
                f"Workspace focus: {len(workspace_metadata.get('focus_paths', []))}; "
                f"knowledge matches: {len(knowledge_metadata.get('matches', []))}; "
                f"personal items: {len(personal_metadata.get('items', []))}; "
                f"warnings: {len(warnings)}."
            ),
            metadata={
                "workspace_context": workspace_metadata,
                "knowledge_context": knowledge_metadata,
                "personal_context": personal_metadata,
            },
        ),
    )
    agent_runs.update_run_status(
        agent_run.id,
        AgentRunStatusUpdate(
            status=AgentRunStatus.RUNNING,
            current_step="Model is responding with assembled context",
            progress_percent=38,
        ),
    )


def _complete_agent_run_if_needed(
    agent_run: AgentRunWithEvents | None,
    agent_runs: AgentRunStore,
    finish_reason: str,
) -> None:
    if agent_run is None:
        return
    if finish_reason == "error":
        _fail_agent_run_if_needed(agent_run, agent_runs, "The model gateway returned an error finish reason.")
        return
    agent_runs.add_event(
        agent_run.id,
        AgentRunEventCreate(
            kind=AgentRunEventKind.STATUS,
            title="Response saved",
            body=f"Assistant response finished with {finish_reason}.",
            metadata={"finish_reason": finish_reason},
        ),
    )
    agent_runs.update_run_status(
        agent_run.id,
        AgentRunStatusUpdate(
            status=AgentRunStatus.COMPLETED,
            current_step="Response saved to chat",
            progress_percent=100,
            metadata={"finish_reason": finish_reason},
        ),
    )


def _fail_agent_run_if_needed(
    agent_run: AgentRunWithEvents | None,
    agent_runs: AgentRunStore,
    detail: str,
) -> None:
    if agent_run is None:
        return
    agent_runs.add_event(
        agent_run.id,
        AgentRunEventCreate(
            kind=AgentRunEventKind.ERROR,
            title="Run failed",
            body=detail,
        ),
    )
    agent_runs.update_run_status(
        agent_run.id,
        AgentRunStatusUpdate(
            status=AgentRunStatus.FAILED,
            current_step=detail,
            progress_percent=100,
        ),
    )


def _resolve_chat_payload(payload: ChatRequest) -> tuple[ChatRequest, dict]:
    resolved_mode, reason = _infer_intent_mode(payload)
    metadata = {
        "requested_mode": payload.mode.value,
        "resolved_mode": resolved_mode.value,
        "agent_enabled": payload.agent_enabled,
        "reason": reason,
    }
    if resolved_mode == payload.mode:
        return payload, metadata
    return payload.model_copy(update={"mode": resolved_mode}), metadata


@dataclass(frozen=True)
class CameraChatResult:
    inference: InferenceResponse
    model_selection: ModelSelection
    artifact: ArtifactRecord | None
    metadata: dict


def _run_camera_chat_action(
    payload: ChatRequest,
    hardware: HardwareDeviceService,
    store: GenerationStore,
    gateway: ModelGateway,
) -> CameraChatResult:
    try:
        _release_camera_feeds(None)
        capture = hardware.capture_camera_snapshot(
            CameraSnapshotRequest(
                width=1280,
                height=720,
                input_format="mjpeg",
                title="Brio camera chat frame",
            )
        )
    except CameraCaptureError as error:
        selection = _camera_tool_selection("Camera capture failed")
        return CameraChatResult(
            inference=InferenceResponse(
                model_id=selection.model.id,
                content=(
                    "I tried to use the camera, but Edison could not capture a frame yet. "
                    f"{error}"
                ),
                finish_reason="error",
                metadata={"tool": "camera.capture", "error": str(error)},
            ),
            model_selection=selection,
            artifact=None,
            metadata={"status": "capture_failed", "error": str(error)},
        )

    artifact = _save_camera_artifact(
        store,
        capture,
        payload.message[:120] or "Brio camera chat frame",
        {"analysis_prompt": payload.message, "source": "chat-camera-intent"},
    )
    image_bytes = capture.absolute_path.read_bytes()
    selection, inference = gateway.analyze_image(_camera_prompt(payload.message), image_bytes, "image/jpeg")
    content = _camera_chat_content(inference, artifact, capture.detail)
    return CameraChatResult(
        inference=InferenceResponse(
            model_id=inference.model_id,
            content=content,
            finish_reason=inference.finish_reason,
            metadata={
                **inference.metadata,
                "tool": "camera.analyze_frame",
                "artifact_id": artifact.id,
                "capture_detail": capture.detail,
            },
        ),
        model_selection=selection,
        artifact=artifact,
        metadata={
            "status": "complete" if inference.finish_reason in {"stop", "length"} else inference.finish_reason,
            "artifact_id": artifact.id,
            "artifact_path": artifact.path,
            "camera": capture.camera.model_dump(mode="json"),
            "capture_detail": capture.detail,
        },
    )


def _camera_chat_content(inference: InferenceResponse, artifact: ArtifactRecord, capture_detail: str) -> str:
    if inference.finish_reason == "not_configured":
        return (
            "I can access the camera now and captured a fresh frame, but the local vision model is not ready yet. "
            f"{inference.content}\n\n"
            f"Saved frame: `{artifact.title}` (`{artifact.id}`)."
        )
    if inference.finish_reason == "error":
        return (
            "I captured a fresh camera frame, but the vision model failed while analyzing it. "
            f"{inference.content}\n\n"
            f"Saved frame: `{artifact.title}` (`{artifact.id}`)."
        )
    return (
        f"{inference.content}\n\n"
        f"Saved frame: `{artifact.title}` (`{artifact.id}`). {capture_detail}"
    )


def _camera_prompt(message: str) -> str:
    return (
        "Analyze this live Edison Brio camera frame in under 120 words. "
        "Start with one direct sentence describing the scene, then list the important visible objects. "
        "If anything is uncertain, say so plainly. User request: "
        f"{message}"
    )


def _camera_tool_selection(reason: str) -> ModelSelection:
    return ModelSelection(
        mode=ChatMode.CHAT,
        required_capabilities=[],
        model=ModelProfile(
            id="edison-camera",
            display_name="Edison Camera",
            provider="edison-hardware",
            status=ModelStatus.READY,
            capabilities=[],
            context_window=0,
            max_output_tokens=0,
        ),
        reason=reason,
    )


def _is_camera_chat_request(message: str) -> bool:
    lowered = message.lower()
    camera_terms = {
        "camera",
        "webcam",
        "brio",
        "video feed",
        "live feed",
        "through your eyes",
        "through the camera",
    }
    visual_terms = {
        "see",
        "seeing",
        "look",
        "watch",
        "visible",
        "view",
        "describe",
        "analyze",
        "snapshot",
        "picture",
        "photo",
        "frame",
    }
    if any(term in lowered for term in camera_terms) and any(term in lowered for term in visual_terms):
        return True
    return any(
        phrase in lowered
        for phrase in (
            "what can you see",
            "what do you see",
            "what are you seeing",
            "look around",
        )
    )


def _infer_intent_mode(payload: ChatRequest) -> tuple[ChatMode, str]:
    if payload.mode != ChatMode.AUTO:
        return payload.mode, "explicit mode selected"
    if payload.agent_enabled:
        return ChatMode.AGENT, "agent toggle enabled"
    if payload.workspace_path or payload.workspace_context_paths:
        return ChatMode.CODING, "workspace context attached"

    message = payload.message.lower()
    words = message.split()
    code_terms = {
        "bug",
        "build",
        "code",
        "commit",
        "css",
        "debug",
        "deploy",
        "fix",
        "function",
        "git",
        "implementation",
        "javascript",
        "patch",
        "python",
        "react",
        "repo",
        "script",
        "typescript",
        "ui",
    }
    if _has_intent_term(message, words, code_terms):
        return ChatMode.CODING, "coding or workspace intent detected"

    research_terms = {
        "compare",
        "deep research",
        "investigate",
        "research",
        "sources",
        "study",
        "summarize",
        "whitepaper",
    }
    reasoning_terms = {
        "analyze",
        "calculate",
        "diagnose",
        "explain why",
        "optimize",
        "plan",
        "reason",
        "solve",
        "troubleshoot",
        "why",
    }
    if _has_intent_term(message, words, research_terms | reasoning_terms):
        return ChatMode.REASONING, "analysis or research intent detected"

    creative_terms = {
        "brainstorm",
        "compose",
        "copywrite",
        "design",
        "draft",
        "rewrite",
        "story",
        "tone",
    }
    if _has_intent_term(message, words, creative_terms):
        return ChatMode.CREATIVE, "creative writing intent detected"

    if len(words) <= 8 and message.endswith("?"):
        return ChatMode.CHAT, "short direct question"
    return ChatMode.CHAT, "general conversation intent"


def _has_intent_term(message: str, words: list[str], terms: set[str]) -> bool:
    token_set = {word.strip(".,;:!?()[]{}\"'`").lower() for word in words}
    for term in terms:
        if " " in term:
            if term in message:
                return True
        elif term in token_set:
            return True
    return False


def _ensure_conversation(payload: ChatRequest, conversations: ConversationStore) -> str:
    if payload.conversation_id:
        conversations.get_conversation(payload.conversation_id)
        return payload.conversation_id
    conversation = conversations.create_conversation(
        ConversationCreate(
            title=_title_from_message(payload.message),
            mode=payload.mode,
            memory_enabled=payload.memory_enabled,
        )
    )
    return conversation.id


def _openai_messages(messages) -> list[dict[str, str]]:
    return [
        {"role": message.role.value, "content": message.content}
        for message in messages[-24:]
        if message.role in {MessageRole.SYSTEM, MessageRole.USER, MessageRole.ASSISTANT}
    ]


def _build_workspace_context(payload: ChatRequest, workspace: WorkspaceTools) -> tuple[list[dict[str, str]], dict]:
    focus_paths = _dedupe_paths(payload.workspace_context_paths)
    if payload.workspace_path:
        focus_paths = [payload.workspace_path, *[path for path in focus_paths if path != payload.workspace_path]]

    metadata = {
        "enabled": payload.include_workspace_context,
        "mode": payload.mode.value,
        "target_path": payload.workspace_path,
        "focus_paths": focus_paths,
        "warnings": [],
        "instruction_files": [],
        "index_matches": [],
    }
    if not payload.include_workspace_context or payload.mode not in {
        ChatMode.CODING,
        ChatMode.AGENT,
        ChatMode.SWARM,
    }:
        return [], metadata

    messages: list[dict[str, str]] = []
    instruction_sections: list[str] = []
    instruction_files: set[str] = set()

    if focus_paths:
        messages.append(
            {
                "role": "system",
                "content": "Focused repository paths for this request:\n" + "\n".join(
                    f"- {path}" for path in focus_paths[:12]
                ),
            }
        )

    for path in focus_paths:
        try:
            instruction_context = workspace.instruction_context(path)
            instruction_files.update(item.path for item in instruction_context.selected_files)
            metadata["warnings"].extend(instruction_context.warnings)
            if instruction_context.combined_text:
                instruction_sections.append(
                    f"### {path}\n{instruction_context.combined_text[:4000]}"
                )
        except WorkspaceNotFoundError:
            metadata["warnings"].append(
                f"Workspace path '{path}' was not found for instruction context."
            )
        except Exception:
            metadata["warnings"].append(
                f"Workspace instruction context for '{path}' could not be loaded."
            )

    metadata["instruction_files"] = sorted(instruction_files)
    if instruction_sections:
        joined_sections = "\n\n".join(instruction_sections)
        messages.append(
            {
                "role": "system",
                "content": (
                    "Repository and path instruction context for this coding task:\n\n"
                    f"{joined_sections[:10000]}"
                ),
            }
        )

    try:
        matches = workspace.search_index(
            WorkspaceIndexSearchRequest(
                query=payload.message,
                max_results=payload.max_workspace_context_matches,
            )
        )
    except Exception:
        matches = []
        metadata["warnings"].append("Workspace semantic index lookup failed.")

    if matches:
        metadata["index_matches"] = [
            {
                "path": item.path,
                "score": item.score,
                "line_number": item.line_number,
            }
            for item in matches
        ]
        lines = []
        for item in matches:
            line_hint = f":{item.line_number}" if item.line_number else ""
            lines.append(f"- {item.path}{line_hint} (score={item.score}): {item.snippet}")
        messages.append(
            {
                "role": "system",
                "content": "Relevant repository snippets for the current request:\n" + "\n".join(lines),
            }
        )

    return messages, metadata


def _build_knowledge_context(payload: ChatRequest, knowledge: KnowledgeStore) -> tuple[list[dict[str, str]], dict]:
    query = (payload.knowledge_query or payload.message or "").strip()
    metadata = {
        "enabled": payload.include_knowledge_context,
        "query": query,
        "warnings": [],
        "matches": [],
    }
    if not payload.include_knowledge_context:
        return [], metadata
    if not query:
        metadata["warnings"].append("Knowledge query is empty.")
        return [], metadata

    try:
        matches = knowledge.search(query, max_results=payload.max_knowledge_context_matches)
    except Exception:
        metadata["warnings"].append("Knowledge lookup failed.")
        return [], metadata

    if not matches:
        metadata["warnings"].append("No knowledge matches found.")
        return [], metadata

    metadata["matches"] = [
        {
            "source_id": item.source_id,
            "source_title": item.source_title,
            "source_kind": item.source_kind,
            "uri": item.uri,
            "path": item.path,
            "score": item.score,
            "snippet": item.snippet,
        }
        for item in matches
    ]
    lines = [
        (
            f"[{index}] [{item.source_kind}] {item.source_title}"
            f"{' <' + item.uri + '>' if item.uri else ''}"
            f" (score={item.score}): {item.snippet}"
        )
        for index, item in enumerate(matches, start=1)
    ]
    return [
        {
            "role": "system",
            "content": (
                "Knowledge base excerpts relevant to this request are below. "
                "Use them when they are relevant, cite the source title or source number, "
                "and say when the provided knowledge does not answer the question.\n"
                + "\n".join(lines)
            ),
        }
    ], metadata


def _build_personal_context(payload: ChatRequest, personal: PersonalWorkspaceStore) -> tuple[list[dict[str, str]], dict]:
    metadata = {
        "enabled": payload.include_personal_context,
        "warnings": [],
        "items": [],
        "documents": [],
    }
    if not payload.include_personal_context or payload.max_personal_context_items <= 0:
        return [], metadata

    try:
        items = personal.list_items(status=OrganizerStatus.ACTIVE, limit=payload.max_personal_context_items)
        documents = personal.search_documents(
            payload.message,
            max_results=max(1, payload.max_personal_context_items // 2),
        )
    except Exception:
        metadata["warnings"].append("Personal workspace context lookup failed.")
        return [], metadata

    metadata["items"] = [
        {
            "id": item.id,
            "kind": item.kind.value,
            "title": item.title,
            "due_at": item.due_at.isoformat() if item.due_at else None,
            "tags": item.tags,
        }
        for item in items
    ]
    metadata["documents"] = [
        {
            "title": document.title,
            "path": document.path,
            "score": document.score,
        }
        for document in documents
    ]
    if not items and not documents:
        return [], metadata

    sections: list[str] = []
    if items:
        item_lines = []
        for item in items:
            due = f", due {item.due_at.isoformat()}" if item.due_at else ""
            tags = f", tags: {', '.join(item.tags)}" if item.tags else ""
            body = f" -- {item.body[:240]}" if item.body else ""
            item_lines.append(f"- [{item.kind.value}] {item.title}{due}{tags}{body}")
        sections.append("Active tasks, notes, and calendar items:\n" + "\n".join(item_lines))
    if documents:
        doc_lines = [
            f"- {document.title} (score={document.score}): {document.snippet}"
            for document in documents
        ]
        sections.append("Relevant saved documents:\n" + "\n".join(doc_lines))

    return [
        {
            "role": "system",
            "content": (
                "Personal Edison context is available for this request. "
                "Use it when it is relevant, but do not invent details beyond these items.\n\n"
                + "\n\n".join(sections)
            ),
        }
    ], metadata


def _dedupe_paths(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for path in paths:
        normalized = path.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:12]


def _title_from_message(message: str) -> str:
    title = " ".join(message.split())
    return f"{title[:53]}..." if len(title) > 56 else title or "New conversation"


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

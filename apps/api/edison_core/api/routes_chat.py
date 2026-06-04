from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from edison_core.api.dependencies import (
    get_conversation_store,
    get_knowledge_store,
    get_model_gateway,
    get_personal_workspace_store,
    get_workspace_tools,
)
from edison_core.schemas import (
    ChatMode,
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    InferenceRequest,
    MessageCreate,
    MessageRole,
    OrganizerStatus,
    WorkspaceIndexSearchRequest,
)
from edison_core.services.conversation_store import ConversationNotFoundError, ConversationStore
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
    knowledge: KnowledgeStore = Depends(get_knowledge_store),
    personal: PersonalWorkspaceStore = Depends(get_personal_workspace_store),
) -> ChatResponse:
    resolved_payload, intent_metadata = _resolve_chat_payload(payload)
    try:
        conversation_id = _ensure_conversation(resolved_payload, conversations)
        workspace_messages, workspace_metadata = _build_workspace_context(resolved_payload, workspace)
        knowledge_messages, knowledge_metadata = _build_knowledge_context(resolved_payload, knowledge)
        personal_messages, personal_metadata = _build_personal_context(resolved_payload, personal)
        context_messages = workspace_messages + knowledge_messages + personal_messages
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
                },
            ),
        )
        conversation = conversations.get_conversation(conversation_id)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found") from error

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
            },
        )
    )
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
    knowledge: KnowledgeStore = Depends(get_knowledge_store),
    personal: PersonalWorkspaceStore = Depends(get_personal_workspace_store),
) -> StreamingResponse:
    resolved_payload, intent_metadata = _resolve_chat_payload(payload)
    try:
        conversation_id = _ensure_conversation(resolved_payload, conversations)
        workspace_messages, workspace_metadata = _build_workspace_context(resolved_payload, workspace)
        knowledge_messages, knowledge_metadata = _build_knowledge_context(resolved_payload, knowledge)
        personal_messages, personal_metadata = _build_personal_context(resolved_payload, personal)
        context_messages = workspace_messages + knowledge_messages + personal_messages
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
                },
            ),
        )
        conversation = conversations.get_conversation(conversation_id)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found") from error

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
            yield _sse("error", {"detail": "Chat stream ended without a final response."})
            return

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

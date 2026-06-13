from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, HTTPException, Query, UploadFile, status

from edison_core.api.dependencies import get_conversation_store, get_knowledge_store
from edison_core.schemas import (
    KnowledgeChatImportResult,
    KnowledgeConversationIngestRequest,
    KnowledgeIngestLocalRequest,
    KnowledgeIngestPresetRequest,
    KnowledgeIngestTextRequest,
    KnowledgeIngestUrlRequest,
    KnowledgeIngestWikipediaRequest,
    KnowledgeSearchMatch,
    KnowledgeSearchRequest,
    KnowledgeSourceRecord,
    KnowledgeStatus,
    KnowledgeWebSearchRequest,
)
from edison_core.services.conversation_store import ConversationNotFoundError, ConversationStore
from edison_core.services.knowledge_store import KnowledgeIngestError, KnowledgeStore


router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


@router.get("/status", response_model=KnowledgeStatus)
def knowledge_status(store: KnowledgeStore = Depends(get_knowledge_store)) -> KnowledgeStatus:
    return store.status()


@router.get("/sources", response_model=list[KnowledgeSourceRecord])
def knowledge_sources(
    limit: int = Query(100, ge=1, le=500),
    store: KnowledgeStore = Depends(get_knowledge_store),
) -> list[KnowledgeSourceRecord]:
    return store.list_sources(limit=limit)


@router.post("/search", response_model=list[KnowledgeSearchMatch])
def knowledge_search(
    payload: KnowledgeSearchRequest,
    store: KnowledgeStore = Depends(get_knowledge_store),
) -> list[KnowledgeSearchMatch]:
    return store.hybrid_search(payload.query, max_results=payload.max_results)


@router.get("/embeddings")
def knowledge_embedding_status(store: KnowledgeStore = Depends(get_knowledge_store)) -> dict:
    return store.embedding_status()


@router.post("/embeddings/run")
def knowledge_embedding_run(
    background: BackgroundTasks,
    max_chunks: int = Query(2000, ge=1, le=200000),
    store: KnowledgeStore = Depends(get_knowledge_store),
) -> dict:
    """Embed a batch of not-yet-embedded chunks in the background (resumable)."""
    background.add_task(store.embed_pending, 64, max_chunks)
    status_now = store.embedding_status()
    return {"started": True, "scheduled_max": max_chunks, **status_now}


@router.get("/profile")
def get_user_profile(store: KnowledgeStore = Depends(get_knowledge_store)) -> dict:
    return store.get_user_profile()


@router.put("/profile")
def set_user_profile(
    text: str = Body("", embed=True),
    store: KnowledgeStore = Depends(get_knowledge_store),
) -> dict:
    return store.set_user_profile_summary(text)


@router.post("/profile/facts")
def add_user_fact(
    text: str = Body(..., embed=True),
    store: KnowledgeStore = Depends(get_knowledge_store),
) -> dict:
    return store.add_user_fact(text)


@router.delete("/profile/facts/{fact_id}")
def delete_user_fact(fact_id: str, store: KnowledgeStore = Depends(get_knowledge_store)) -> dict:
    return store.delete_user_fact(fact_id)


@router.post("/profile/rebuild")
def rebuild_user_profile(store: KnowledgeStore = Depends(get_knowledge_store)) -> dict:
    """Extract a fresh profile of the user from imported conversation memory."""
    try:
        return store.build_user_profile()
    except KnowledgeIngestError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/ingest/text", response_model=KnowledgeSourceRecord, status_code=status.HTTP_201_CREATED)
def ingest_text(
    payload: KnowledgeIngestTextRequest,
    store: KnowledgeStore = Depends(get_knowledge_store),
) -> KnowledgeSourceRecord:
    try:
        return store.ingest_text(payload)
    except KnowledgeIngestError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/ingest/url", response_model=KnowledgeSourceRecord, status_code=status.HTTP_201_CREATED)
def ingest_url(
    payload: KnowledgeIngestUrlRequest,
    store: KnowledgeStore = Depends(get_knowledge_store),
) -> KnowledgeSourceRecord:
    try:
        return store.ingest_url(
            payload.url,
            title=payload.title,
            language=payload.language,
            license_name=payload.license,
        )
    except KnowledgeIngestError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Knowledge download failed: {error}") from error


@router.post("/ingest/wikipedia", response_model=KnowledgeSourceRecord, status_code=status.HTTP_201_CREATED)
def ingest_wikipedia(
    payload: KnowledgeIngestWikipediaRequest,
    store: KnowledgeStore = Depends(get_knowledge_store),
) -> KnowledgeSourceRecord:
    try:
        return store.ingest_wikipedia_page(payload.title, payload.language)
    except KnowledgeIngestError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Wikipedia ingest failed: {error}") from error


@router.post("/ingest/local", response_model=list[KnowledgeSourceRecord], status_code=status.HTTP_201_CREATED)
def ingest_local(
    payload: KnowledgeIngestLocalRequest,
    store: KnowledgeStore = Depends(get_knowledge_store),
) -> list[KnowledgeSourceRecord]:
    try:
        return store.ingest_local(payload)
    except KnowledgeIngestError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/ingest/preset", response_model=list[KnowledgeSourceRecord], status_code=status.HTTP_201_CREATED)
def ingest_preset(
    payload: KnowledgeIngestPresetRequest,
    store: KnowledgeStore = Depends(get_knowledge_store),
) -> list[KnowledgeSourceRecord]:
    try:
        return store.ingest_preset(payload.preset)
    except KnowledgeIngestError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Preset ingest failed: {error}") from error


@router.post(
    "/ingest/chat-export",
    response_model=KnowledgeChatImportResult,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_chat_export(
    files: list[UploadFile] = File(...),
    source: str = Form("auto"),
    store: KnowledgeStore = Depends(get_knowledge_store),
) -> KnowledgeChatImportResult:
    """Import ChatGPT/Claude data exports (conversations.json or the export .zip)."""
    if source not in {"auto", "chatgpt", "claude"}:
        raise HTTPException(status_code=400, detail="source must be 'auto', 'chatgpt', or 'claude'.")

    imported: list[KnowledgeSourceRecord] = []
    total_conversations = 0
    skipped = 0
    detected_sources: set[str] = set()
    errors: list[str] = []

    for upload in files:
        raw = await upload.read()
        if not raw:
            continue
        if len(raw) > 80 * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f"{upload.filename or 'file'} is too large (max 80 MB).",
            )
        try:
            result = store.ingest_chat_export(raw, filename=upload.filename or "", source_hint=source)
        except KnowledgeIngestError as error:
            errors.append(f"{upload.filename or 'file'}: {error}")
            continue
        imported.extend(result.sources)
        total_conversations += result.conversation_count
        skipped += result.skipped_count
        detected_sources.add(result.detected_source)

    if not imported:
        detail = "; ".join(errors) if errors else "No conversations could be imported from the uploaded files."
        raise HTTPException(status_code=400, detail=detail)

    if len(detected_sources) == 1:
        detected = next(iter(detected_sources))
    elif detected_sources:
        detected = "mixed"
    else:
        detected = "unknown"

    return KnowledgeChatImportResult(
        detected_source=detected,
        conversation_count=total_conversations,
        imported_count=len(imported),
        skipped_count=skipped,
        sources=imported[:200],
    )


@router.post("/ingest/web-search", response_model=list[KnowledgeSourceRecord], status_code=status.HTTP_201_CREATED)
def ingest_web_search(
    payload: KnowledgeWebSearchRequest,
    store: KnowledgeStore = Depends(get_knowledge_store),
) -> list[KnowledgeSourceRecord]:
    """Search the web (DuckDuckGo) and store the top results into the knowledge base."""
    try:
        return store.ingest_web_search(payload.query, max_results=payload.max_results)
    except KnowledgeIngestError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Web search failed: {error}") from error


@router.post("/ingest/conversation", response_model=KnowledgeSourceRecord, status_code=status.HTTP_201_CREATED)
def ingest_conversation(
    payload: KnowledgeConversationIngestRequest,
    store: KnowledgeStore = Depends(get_knowledge_store),
    conversations: ConversationStore = Depends(get_conversation_store),
) -> KnowledgeSourceRecord:
    """Remember a conversation by ingesting its transcript into the knowledge base."""
    try:
        conversation = conversations.get_conversation(payload.conversation_id)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error
    try:
        return store.ingest_conversation(conversation)
    except KnowledgeIngestError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

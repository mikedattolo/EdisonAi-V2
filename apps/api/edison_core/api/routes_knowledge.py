from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from edison_core.api.dependencies import get_knowledge_store
from edison_core.schemas import (
    KnowledgeChatImportResult,
    KnowledgeIngestLocalRequest,
    KnowledgeIngestPresetRequest,
    KnowledgeIngestTextRequest,
    KnowledgeIngestUrlRequest,
    KnowledgeIngestWikipediaRequest,
    KnowledgeSearchMatch,
    KnowledgeSearchRequest,
    KnowledgeSourceRecord,
    KnowledgeStatus,
)
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
    return store.search(payload.query, max_results=payload.max_results)


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

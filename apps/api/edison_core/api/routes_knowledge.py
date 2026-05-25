from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from edison_core.api.dependencies import get_knowledge_store
from edison_core.schemas import (
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

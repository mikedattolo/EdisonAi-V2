from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from edison_core.api.dependencies import (
    get_knowledge_store,
    get_personal_workspace_store,
    get_workspace_tools,
)
from edison_core.schemas import (
    DocumentCreate,
    DocumentRecord,
    DocumentUpdate,
    KnowledgeIngestTextRequest,
    KnowledgeSourceRecord,
    OrganizerItemCreate,
    OrganizerItemRecord,
    OrganizerItemUpdate,
    OrganizerKind,
    OrganizerStatus,
    SearchCompareRequest,
    SearchCompareResponse,
    SearchCompareResult,
    SearchProvider,
    WorkspaceIndexSearchRequest,
)
from edison_core.services.knowledge_store import KnowledgeStore
from edison_core.services.personal_workspace import (
    PersonalWorkspaceNotFoundError,
    PersonalWorkspaceStore,
)
from edison_core.services.workspace_tools import WorkspaceTools


router = APIRouter(prefix="/api/v1", tags=["personal-workspace"])


@router.get("/organizer/items", response_model=list[OrganizerItemRecord])
def list_organizer_items(
    kind: OrganizerKind | None = Query(default=None),
    item_status: OrganizerStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=300),
    store: PersonalWorkspaceStore = Depends(get_personal_workspace_store),
) -> list[OrganizerItemRecord]:
    return store.list_items(kind=kind, status=item_status, limit=limit)


@router.post("/organizer/items", response_model=OrganizerItemRecord, status_code=status.HTTP_201_CREATED)
def create_organizer_item(
    payload: OrganizerItemCreate,
    store: PersonalWorkspaceStore = Depends(get_personal_workspace_store),
) -> OrganizerItemRecord:
    return store.create_item(payload)


@router.put("/organizer/items/{item_id}", response_model=OrganizerItemRecord)
def update_organizer_item(
    item_id: str,
    payload: OrganizerItemUpdate,
    store: PersonalWorkspaceStore = Depends(get_personal_workspace_store),
) -> OrganizerItemRecord:
    try:
        return store.update_item(item_id, payload)
    except PersonalWorkspaceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organizer item not found") from error


@router.delete("/organizer/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organizer_item(
    item_id: str,
    store: PersonalWorkspaceStore = Depends(get_personal_workspace_store),
) -> Response:
    try:
        store.delete_item(item_id)
    except PersonalWorkspaceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organizer item not found") from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/documents", response_model=list[DocumentRecord])
def list_documents(
    limit: int = Query(default=100, ge=1, le=300),
    store: PersonalWorkspaceStore = Depends(get_personal_workspace_store),
) -> list[DocumentRecord]:
    return store.list_documents(limit=limit)


@router.post("/documents", response_model=DocumentRecord, status_code=status.HTTP_201_CREATED)
def create_document(
    payload: DocumentCreate,
    store: PersonalWorkspaceStore = Depends(get_personal_workspace_store),
) -> DocumentRecord:
    return store.create_document(payload)


@router.put("/documents/{document_id}", response_model=DocumentRecord)
def update_document(
    document_id: str,
    payload: DocumentUpdate,
    store: PersonalWorkspaceStore = Depends(get_personal_workspace_store),
) -> DocumentRecord:
    try:
        return store.update_document(document_id, payload)
    except PersonalWorkspaceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found") from error


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    store: PersonalWorkspaceStore = Depends(get_personal_workspace_store),
) -> Response:
    try:
        store.delete_document(document_id)
    except PersonalWorkspaceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found") from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/documents/{document_id}/ingest", response_model=KnowledgeSourceRecord, status_code=status.HTTP_201_CREATED)
def ingest_document(
    document_id: str,
    store: PersonalWorkspaceStore = Depends(get_personal_workspace_store),
    knowledge: KnowledgeStore = Depends(get_knowledge_store),
) -> KnowledgeSourceRecord:
    try:
        document = store.get_document(document_id)
    except PersonalWorkspaceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found") from error
    return knowledge.ingest_text(
        KnowledgeIngestTextRequest(
            title=f"Document: {document.title}",
            text=document.content or document.title,
            uri=f"edison://documents/{document.id}",
            metadata={"source": "document", "document_id": document.id, "tags": document.tags},
        ),
        kind="text",
    )


@router.post("/search/compare", response_model=SearchCompareResponse)
def compare_search(
    payload: SearchCompareRequest,
    store: PersonalWorkspaceStore = Depends(get_personal_workspace_store),
    knowledge: KnowledgeStore = Depends(get_knowledge_store),
    workspace: WorkspaceTools = Depends(get_workspace_tools),
) -> SearchCompareResponse:
    providers = list(dict.fromkeys(payload.providers))
    results: dict[SearchProvider, list[SearchCompareResult]] = {}

    if SearchProvider.KNOWLEDGE in providers:
        results[SearchProvider.KNOWLEDGE] = [
            SearchCompareResult(
                provider=SearchProvider.KNOWLEDGE,
                title=match.source_title,
                subtitle=match.source_kind,
                snippet=match.snippet,
                score=match.score,
                uri=match.uri,
                path=match.path,
                metadata={"source_id": match.source_id},
            )
            for match in knowledge.search(payload.query, max_results=payload.max_results)
        ]

    if SearchProvider.WORKSPACE in providers:
        results[SearchProvider.WORKSPACE] = [
            SearchCompareResult(
                provider=SearchProvider.WORKSPACE,
                title=match.path,
                subtitle=match.language,
                snippet=match.snippet,
                score=match.score,
                path=match.path,
                metadata={"line_number": match.line_number},
            )
            for match in workspace.search_index(
                WorkspaceIndexSearchRequest(query=payload.query, max_results=payload.max_results)
            )
        ]

    if SearchProvider.DOCUMENTS in providers:
        results[SearchProvider.DOCUMENTS] = store.search_documents(payload.query, max_results=payload.max_results)

    provider_counts = {provider: len(provider_results) for provider, provider_results in results.items()}
    best_provider = max(provider_counts, key=provider_counts.get) if provider_counts else None
    return SearchCompareResponse(
        query=payload.query,
        results=results,
        provider_counts=provider_counts,
        best_provider=best_provider,
    )

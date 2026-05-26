from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from edison_core.api.dependencies import (
    get_comfyui_client,
    get_conversation_store,
    get_generation_store,
    get_invokeai_client,
    get_media_orchestrator,
    get_modly_client,
    get_wan22_client,
)
from edison_core.schemas import (
    JobCreate,
    JobRecord,
    JobStatus,
    MediaJobDeliveryRequest,
    MediaSystemStatus,
    MessageCreate,
    MessageRecord,
    MessageRole,
)
from edison_core.services.comfyui_client import ComfyUIClient
from edison_core.services.conversation_store import ConversationNotFoundError, ConversationStore
from edison_core.services.generation_store import GenerationStore, JobNotFoundError
from edison_core.services.invokeai_client import InvokeAIClient
from edison_core.services.media_orchestrator import MediaOrchestrator
from edison_core.services.modly_client import ModlyClient
from edison_core.services.wan22_client import Wan22Client


router = APIRouter(prefix="/api/v1/media", tags=["media"])


@router.get("/status", response_model=MediaSystemStatus)
def media_status(
    comfyui: ComfyUIClient = Depends(get_comfyui_client),
    invokeai: InvokeAIClient = Depends(get_invokeai_client),
    wan22: Wan22Client = Depends(get_wan22_client),
    modly: ModlyClient = Depends(get_modly_client),
    store: GenerationStore = Depends(get_generation_store),
) -> MediaSystemStatus:
    return MediaSystemStatus(
        comfyui=comfyui.status(),
        invokeai=invokeai.status(),
        wan22=wan22.status(),
        modly=modly.status(),
        job_counts=store.job_counts(),
    )


@router.post("/jobs", response_model=JobRecord, status_code=status.HTTP_201_CREATED)
def create_media_job(
    payload: JobCreate,
    comfyui: ComfyUIClient = Depends(get_comfyui_client),
    invokeai: InvokeAIClient = Depends(get_invokeai_client),
    wan22: Wan22Client = Depends(get_wan22_client),
    modly: ModlyClient = Depends(get_modly_client),
    orchestrator: MediaOrchestrator = Depends(get_media_orchestrator),
    store: GenerationStore = Depends(get_generation_store),
) -> JobRecord:
    selected_backend = _resolve_backend(payload)
    backend_status = _backend_status(selected_backend, comfyui, invokeai, wan22, modly)
    payload.backend = selected_backend
    payload.metadata = {
        **payload.metadata,
        "backend_status": backend_status.model_dump(mode="json"),
        "backend": selected_backend,
    }
    if backend_status.status != "ready":
        job = store.create_job(payload, status=JobStatus.SETUP_REQUIRED)
        store.add_event(
            job.id,
            JobStatus.SETUP_REQUIRED,
            backend_status.detail,
            {"base_url": backend_status.base_url, "backend": selected_backend},
        )
        return job
    return orchestrator.submit_job(payload, store)


@router.post("/jobs/{job_id}/sync", response_model=JobRecord)
def sync_media_job(
    job_id: str,
    orchestrator: MediaOrchestrator = Depends(get_media_orchestrator),
    store: GenerationStore = Depends(get_generation_store),
) -> JobRecord:
    return orchestrator.sync_job(job_id, store)


@router.post("/jobs/{job_id}/cancel", response_model=JobRecord)
def cancel_media_job(
    job_id: str,
    orchestrator: MediaOrchestrator = Depends(get_media_orchestrator),
    store: GenerationStore = Depends(get_generation_store),
) -> JobRecord:
    return orchestrator.cancel_job(job_id, store)


@router.post("/jobs/{job_id}/deliver", response_model=MessageRecord, status_code=status.HTTP_201_CREATED)
def deliver_media_job_to_chat(
    job_id: str,
    payload: MediaJobDeliveryRequest,
    store: GenerationStore = Depends(get_generation_store),
    conversations: ConversationStore = Depends(get_conversation_store),
) -> MessageRecord:
    try:
        job = store.get_job(job_id)
    except JobNotFoundError as error:
        raise HTTPException(status_code=404, detail="Job not found") from error

    conversation_id = payload.conversation_id or _string_metadata(job.metadata, "conversation_id")
    if not conversation_id:
        raise HTTPException(status_code=400, detail="No conversation id was provided for delivery.")
    if job.status != JobStatus.COMPLETE or not job.result_artifact_id:
        raise HTTPException(status_code=409, detail="Media job does not have a completed artifact yet.")

    existing_message_id = _string_metadata(job.metadata, "delivered_message_id")
    if existing_message_id:
        try:
            conversation = conversations.get_conversation(conversation_id)
        except ConversationNotFoundError as error:
            raise HTTPException(status_code=404, detail="Conversation not found") from error
        for message in conversation.messages:
            if message.id == existing_message_id:
                return message

    try:
        artifact = store.get_artifact(job.result_artifact_id)
    except JobNotFoundError as error:
        raise HTTPException(status_code=404, detail="Generated artifact not found") from error

    try:
        message = conversations.add_message(
            conversation_id,
            MessageCreate(
                role=MessageRole.ASSISTANT,
                content=f"Done. I generated {artifact.kind.value} output for {job.title}.",
                model=job.backend,
                metadata={
                    "delivery_type": "media_result",
                    "media_job": job.model_dump(mode="json"),
                    "artifacts": [artifact.model_dump(mode="json")],
                },
            ),
        )
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found") from error

    store.update_job_status(
        job.id,
        job.status,
        "Media result delivered to chat.",
        {"delivered_message_id": message.id, "conversation_id": conversation_id},
    )
    return message


def _resolve_backend(payload: JobCreate) -> str:
    requested = (payload.backend or "").strip().lower()
    if requested in {"comfyui", "invokeai", "wan22", "modly"}:
        return requested
    if payload.job_type == "video":
        return "wan22"
    if payload.job_type == "mesh":
        return "modly"
    return "comfyui"


def _backend_status(
    backend: str,
    comfyui: ComfyUIClient,
    invokeai: InvokeAIClient,
    wan22: Wan22Client,
    modly: ModlyClient,
):
    if backend == "invokeai":
        return invokeai.status()
    if backend == "wan22":
        return wan22.status()
    if backend == "modly":
        return modly.status()
    return comfyui.status()


def _string_metadata(payload: dict, key: str) -> str | None:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None

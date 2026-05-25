from __future__ import annotations

from fastapi import APIRouter, Depends, status

from edison_core.api.dependencies import (
    get_comfyui_client,
    get_generation_store,
    get_invokeai_client,
    get_media_orchestrator,
    get_modly_client,
    get_wan22_client,
)
from edison_core.schemas import JobCreate, JobRecord, JobStatus, MediaSystemStatus
from edison_core.services.comfyui_client import ComfyUIClient
from edison_core.services.generation_store import GenerationStore
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
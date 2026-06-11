from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from edison_core.api.dependencies import get_creator_lab_service, get_creator_training_service
from edison_core.schemas import (
    CreatorLabDataset,
    CreatorLabDatasetCreateRequest,
    CreatorLabOverview,
    CreatorLabSelectionRequest,
    CreatorTrainingConfig,
    CreatorTrainingJob,
    CreatorVlmCritique,
    CreatorVlmCritiqueRequest,
    CreatorWorkflowGraph,
)
from edison_core.services.creator_lab import CreatorLabError, CreatorLabService
from edison_core.services.creator_training import CreatorTrainingError, CreatorTrainingService

router = APIRouter(prefix="/api/v1/creator-lab", tags=["creator-lab"])


def _handle(error: CreatorLabError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.message)


@router.get("/overview", response_model=CreatorLabOverview)
def creator_lab_overview(service: CreatorLabService = Depends(get_creator_lab_service)) -> CreatorLabOverview:
    return service.overview()


@router.get("/datasets", response_model=list[CreatorLabDataset])
def list_datasets(service: CreatorLabService = Depends(get_creator_lab_service)) -> list[CreatorLabDataset]:
    return service.list_datasets()


@router.post("/datasets", response_model=CreatorLabDataset)
def create_dataset(
    payload: CreatorLabDatasetCreateRequest,
    service: CreatorLabService = Depends(get_creator_lab_service),
) -> CreatorLabDataset:
    try:
        return service.create_dataset(payload)
    except CreatorLabError as error:
        raise _handle(error)


@router.get("/datasets/{dataset_id}", response_model=CreatorLabDataset)
def get_dataset(dataset_id: str, service: CreatorLabService = Depends(get_creator_lab_service)) -> CreatorLabDataset:
    try:
        return service.get_dataset(dataset_id)
    except CreatorLabError as error:
        raise _handle(error)


@router.delete("/datasets/{dataset_id}")
def delete_dataset(dataset_id: str, service: CreatorLabService = Depends(get_creator_lab_service)) -> dict:
    service.delete_dataset(dataset_id)
    return {"status": "deleted", "dataset_id": dataset_id}


@router.post("/datasets/{dataset_id}/images", response_model=CreatorLabDataset)
async def upload_images(
    dataset_id: str,
    files: list[UploadFile] = File(...),
    service: CreatorLabService = Depends(get_creator_lab_service),
) -> CreatorLabDataset:
    payload: list[tuple[str, bytes]] = []
    for upload in files:
        data = await upload.read()
        payload.append((upload.filename or "image.png", data))
    try:
        return service.add_images(dataset_id, payload)
    except CreatorLabError as error:
        raise _handle(error)


@router.get("/datasets/{dataset_id}/images/{image_id}")
def get_image(
    dataset_id: str,
    image_id: str,
    service: CreatorLabService = Depends(get_creator_lab_service),
) -> FileResponse:
    try:
        path = service.image_file(dataset_id, image_id)
    except CreatorLabError as error:
        raise _handle(error)
    return FileResponse(path)


@router.delete("/datasets/{dataset_id}/images/{image_id}", response_model=CreatorLabDataset)
def delete_image(
    dataset_id: str,
    image_id: str,
    service: CreatorLabService = Depends(get_creator_lab_service),
) -> CreatorLabDataset:
    try:
        return service.delete_image(dataset_id, image_id)
    except CreatorLabError as error:
        raise _handle(error)


@router.post("/selection", response_model=CreatorLabOverview)
def set_selection(
    payload: CreatorLabSelectionRequest,
    service: CreatorLabService = Depends(get_creator_lab_service),
) -> CreatorLabOverview:
    return service.set_selection(payload)


@router.get("/workflows/{workflow_id}/graph", response_model=CreatorWorkflowGraph)
def workflow_graph(
    workflow_id: str,
    service: CreatorLabService = Depends(get_creator_lab_service),
) -> CreatorWorkflowGraph:
    try:
        return service.workflow_graph(workflow_id)
    except CreatorLabError as error:
        raise _handle(error)


@router.post("/vlm-critique", response_model=CreatorVlmCritique)
def vlm_critique(
    payload: CreatorVlmCritiqueRequest,
    service: CreatorLabService = Depends(get_creator_lab_service),
) -> CreatorVlmCritique:
    image_bytes = _load_image_bytes(payload, service)
    if image_bytes is None:
        raise HTTPException(status_code=400, detail="Provide a dataset image (dataset_id+image_id) or an image_url to critique.")
    return service.vlm_critique(image_bytes, payload.prompt, payload.question)


@router.post("/training/start", response_model=CreatorTrainingJob)
def start_training(
    payload: CreatorTrainingConfig,
    service: CreatorLabService = Depends(get_creator_lab_service),
    training: CreatorTrainingService = Depends(get_creator_training_service),
) -> CreatorTrainingJob:
    try:
        dataset = service.get_dataset(payload.dataset_id)
    except CreatorLabError as error:
        raise _handle(error)
    try:
        return training.start(payload, dataset)
    except CreatorTrainingError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message)


@router.get("/training/jobs", response_model=list[CreatorTrainingJob])
def list_training_jobs(training: CreatorTrainingService = Depends(get_creator_training_service)) -> list[CreatorTrainingJob]:
    return training.list_jobs()


@router.get("/training/jobs/{job_id}", response_model=CreatorTrainingJob)
def get_training_job(
    job_id: str,
    training: CreatorTrainingService = Depends(get_creator_training_service),
) -> CreatorTrainingJob:
    try:
        return training.get_job(job_id)
    except CreatorTrainingError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message)


@router.post("/training/jobs/{job_id}/cancel", response_model=CreatorTrainingJob)
def cancel_training_job(
    job_id: str,
    training: CreatorTrainingService = Depends(get_creator_training_service),
) -> CreatorTrainingJob:
    try:
        return training.cancel(job_id)
    except CreatorTrainingError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message)


def _load_image_bytes(payload: CreatorVlmCritiqueRequest, service: CreatorLabService) -> bytes | None:
    if payload.dataset_id and payload.image_id:
        try:
            return service.image_file(payload.dataset_id, payload.image_id).read_bytes()
        except CreatorLabError:
            return None
    url = (payload.image_url or "").strip()
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        try:
            response = httpx.get(url, timeout=30.0)
            if response.status_code < 400:
                return response.content
        except httpx.HTTPError:
            return None
        return None
    # Local artifact path (e.g. a ComfyUI output under the artifact root).
    candidate = Path(url)
    if candidate.exists() and candidate.is_file():
        return candidate.read_bytes()
    return None

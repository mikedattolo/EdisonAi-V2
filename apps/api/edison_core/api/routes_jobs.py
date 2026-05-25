from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from edison_core.api.dependencies import get_generation_store
from edison_core.schemas import ArtifactRecord, JobCreate, JobEventRecord, JobRecord, JobStatus, JobType
from edison_core.services.generation_store import GenerationStore, JobNotFoundError


router = APIRouter(prefix="/api/v1", tags=["jobs"])


@router.get("/artifacts", response_model=list[ArtifactRecord])
def list_artifacts(
    limit: int = Query(50, ge=1, le=200),
    store: GenerationStore = Depends(get_generation_store),
) -> list[ArtifactRecord]:
    return store.list_artifacts(limit=limit)


@router.get("/artifacts/{artifact_id}", response_model=ArtifactRecord)
def get_artifact(
    artifact_id: str,
    store: GenerationStore = Depends(get_generation_store),
) -> ArtifactRecord:
    try:
        return store.get_artifact(artifact_id)
    except JobNotFoundError as error:
        raise HTTPException(status_code=404, detail="Artifact not found") from error


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(
    artifact_id: str,
    request: Request,
    store: GenerationStore = Depends(get_generation_store),
) -> FileResponse:
    try:
        artifact = store.get_artifact(artifact_id)
    except JobNotFoundError as error:
        raise HTTPException(status_code=404, detail="Artifact not found") from error

    settings = request.app.state.settings
    candidate = _resolve_artifact_path(Path(artifact.path), settings.artifact_root)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Artifact file not found")
    return FileResponse(candidate, media_type=artifact.mime_type, filename=candidate.name)


@router.post("/jobs", response_model=JobRecord, status_code=status.HTTP_201_CREATED)
def create_job(
    payload: JobCreate,
    store: GenerationStore = Depends(get_generation_store),
) -> JobRecord:
    return store.create_job(payload)


@router.get("/jobs", response_model=list[JobRecord])
def list_jobs(
    job_type: JobType | None = None,
    job_status: JobStatus | None = None,
    limit: int = Query(50, ge=1, le=200),
    store: GenerationStore = Depends(get_generation_store),
) -> list[JobRecord]:
    return store.list_jobs(job_type=job_type, status=job_status, limit=limit)


@router.get("/jobs/{job_id}", response_model=JobRecord)
def get_job(
    job_id: str,
    store: GenerationStore = Depends(get_generation_store),
) -> JobRecord:
    try:
        return store.get_job(job_id)
    except JobNotFoundError as error:
        raise HTTPException(status_code=404, detail="Job not found") from error


@router.post("/jobs/{job_id}/cancel", response_model=JobRecord)
def cancel_job(
    job_id: str,
    store: GenerationStore = Depends(get_generation_store),
) -> JobRecord:
    try:
        return store.update_job_status(job_id, JobStatus.CANCELLED, "Job cancelled by user request")
    except JobNotFoundError as error:
        raise HTTPException(status_code=404, detail="Job not found") from error


@router.get("/jobs/{job_id}/events", response_model=list[JobEventRecord])
def list_job_events(
    job_id: str,
    store: GenerationStore = Depends(get_generation_store),
) -> list[JobEventRecord]:
    try:
        return store.list_events(job_id)
    except JobNotFoundError as error:
        raise HTTPException(status_code=404, detail="Job not found") from error


def _resolve_artifact_path(path: Path, artifact_root: Path) -> Path | None:
    if path.is_absolute() and path.exists():
        return path
    candidates = [artifact_root / path, artifact_root.parent / path]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None
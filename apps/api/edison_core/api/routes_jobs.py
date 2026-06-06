from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response

from edison_core.api.dependencies import get_generation_store
from edison_core.schemas import ArtifactCreate, ArtifactKind, ArtifactRecord, JobCreate, JobEventRecord, JobRecord, JobStatus, JobType
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


@router.post("/artifacts/upload", response_model=ArtifactRecord, status_code=status.HTTP_201_CREATED)
async def upload_artifact(
    request: Request,
    file: UploadFile = File(...),
    store: GenerationStore = Depends(get_generation_store),
) -> ArtifactRecord:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Uploaded file is too large.")

    settings = request.app.state.settings
    suffix = Path(file.filename).suffix.lower() or ".bin"
    safe_name = f"upload-{uuid4().hex}{suffix}"
    upload_dir = settings.artifact_root / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    output_path = upload_dir / safe_name
    output_path.write_bytes(content)
    mime_type = file.content_type or "application/octet-stream"
    return store.create_artifact(
        ArtifactCreate(
            kind=_artifact_kind_from_mime(mime_type),
            title=Path(file.filename).stem[:120] or "Reference upload",
            path=output_path.relative_to(settings.artifact_root.parent).as_posix(),
            mime_type=mime_type,
            metadata={"source": "upload", "original_filename": file.filename},
        )
    )


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


@router.delete(
    "/artifacts/{artifact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def delete_artifact(
    artifact_id: str,
    request: Request,
    delete_file: bool = Query(True),
    store: GenerationStore = Depends(get_generation_store),
) -> None:
    try:
        artifact = store.delete_artifact(artifact_id)
    except JobNotFoundError as error:
        raise HTTPException(status_code=404, detail="Artifact not found") from error

    if delete_file:
        settings = request.app.state.settings
        _delete_artifact_file(Path(artifact.path), settings.artifact_root)


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


@router.delete(
    "/jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def delete_job(
    job_id: str,
    store: GenerationStore = Depends(get_generation_store),
) -> None:
    try:
        store.delete_job(job_id)
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


def _delete_artifact_file(path: Path, artifact_root: Path) -> None:
    candidate = _resolve_artifact_path(path, artifact_root)
    if candidate is None or not candidate.is_file():
        return
    artifact_root_resolved = artifact_root.resolve()
    candidate_resolved = candidate.resolve()
    if not candidate_resolved.is_relative_to(artifact_root_resolved):
        return
    candidate_resolved.unlink(missing_ok=True)


def _artifact_kind_from_mime(mime_type: str) -> ArtifactKind:
    if mime_type.startswith("image/"):
        return ArtifactKind.IMAGE
    if mime_type.startswith("video/"):
        return ArtifactKind.VIDEO
    if mime_type.startswith("audio/"):
        return ArtifactKind.AUDIO
    return ArtifactKind.OTHER

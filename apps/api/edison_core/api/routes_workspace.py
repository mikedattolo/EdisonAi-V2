from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from edison_core.api.dependencies import get_generation_store, get_workspace_tools
from edison_core.schemas import (
    JobCreate,
    JobStatus,
    JobType,
    WorkspaceEntry,
    WorkspaceFile,
    WorkspaceCommandRunRequest,
    WorkspaceCommandRunResult,
    WorkspacePatchApplyRequest,
    WorkspacePatchApplyResult,
    WorkspacePatchPreview,
    WorkspacePatchRequest,
    WorkspaceSearchMatch,
    WorkspaceSearchRequest,
    WorkspaceScan,
    WorkspaceSummary,
    WorkspaceInstructionContext,
    WorkspaceInstructionFile,
    WorkspaceIndexSearchMatch,
    WorkspaceIndexSearchRequest,
    WorkspaceIndexStatus,
)
from edison_core.services.workspace_tools import (
    WorkspaceAccessError,
    WorkspaceCommandApprovalError,
    WorkspaceCommandNotAllowedError,
    WorkspaceNotFoundError,
    WorkspacePatchApprovalError,
    WorkspacePatchConflictError,
    WorkspaceTools,
    WorkspaceUnsupportedFileError,
)
from edison_core.services.generation_store import GenerationStore


router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])


@router.get("/summary", response_model=WorkspaceSummary)
def workspace_summary(workspace: WorkspaceTools = Depends(get_workspace_tools)) -> WorkspaceSummary:
    return workspace.summarize()


@router.get("/scan", response_model=WorkspaceScan)
def workspace_scan(workspace: WorkspaceTools = Depends(get_workspace_tools)) -> WorkspaceScan:
    return workspace.scan()


@router.get("/files", response_model=list[WorkspaceEntry])
def list_workspace_files(
    path: str = "",
    limit: int = Query(200, ge=1, le=500),
    workspace: WorkspaceTools = Depends(get_workspace_tools),
) -> list[WorkspaceEntry]:
    try:
        return workspace.list_directory(path, limit=limit)
    except WorkspaceAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except WorkspaceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.get("/files/content", response_model=WorkspaceFile)
def read_workspace_file(
    path: str = Query(..., min_length=1),
    workspace: WorkspaceTools = Depends(get_workspace_tools),
) -> WorkspaceFile:
    try:
        return workspace.read_file(path)
    except WorkspaceAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except WorkspaceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except WorkspaceUnsupportedFileError as error:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(error)) from error


@router.post("/search", response_model=list[WorkspaceSearchMatch])
def search_workspace(
    payload: WorkspaceSearchRequest,
    workspace: WorkspaceTools = Depends(get_workspace_tools),
) -> list[WorkspaceSearchMatch]:
    return workspace.search(payload)


@router.get("/instructions", response_model=list[WorkspaceInstructionFile])
def list_workspace_instructions(
    limit: int = Query(200, ge=1, le=500),
    workspace: WorkspaceTools = Depends(get_workspace_tools),
) -> list[WorkspaceInstructionFile]:
    return workspace.list_instruction_files(limit=limit)


@router.get("/instructions/context", response_model=WorkspaceInstructionContext)
def workspace_instruction_context(
    path: str = Query(..., min_length=1),
    workspace: WorkspaceTools = Depends(get_workspace_tools),
) -> WorkspaceInstructionContext:
    try:
        return workspace.instruction_context(path)
    except WorkspaceAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except WorkspaceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.get("/index/status", response_model=WorkspaceIndexStatus)
def workspace_index_status(workspace: WorkspaceTools = Depends(get_workspace_tools)) -> WorkspaceIndexStatus:
    return workspace.index_status()


@router.post("/index/rebuild", response_model=WorkspaceIndexStatus)
def workspace_index_rebuild(
    workspace: WorkspaceTools = Depends(get_workspace_tools),
    store: GenerationStore = Depends(get_generation_store),
) -> WorkspaceIndexStatus:
    job = store.create_job(
        JobCreate(
            job_type=JobType.CODE,
            title="Rebuild workspace index",
            backend="workspace-index",
            metadata={},
        )
    )
    running_job = store.update_job_status(job.id, JobStatus.GENERATING, "Workspace index rebuild started", {})
    status_payload = workspace.rebuild_index()
    store.update_job_status(
        running_job.id,
        JobStatus.COMPLETE,
        "Workspace index rebuild completed",
        {
            "indexed_file_count": status_payload.indexed_file_count,
            "is_stale": status_payload.is_stale,
            "index_built_at": status_payload.index_built_at.isoformat()
            if status_payload.index_built_at
            else None,
        },
    )
    return status_payload


@router.post("/index/search", response_model=list[WorkspaceIndexSearchMatch])
def workspace_index_search(
    payload: WorkspaceIndexSearchRequest,
    workspace: WorkspaceTools = Depends(get_workspace_tools),
) -> list[WorkspaceIndexSearchMatch]:
    return workspace.search_index(payload)


@router.post("/patches/preview", response_model=WorkspacePatchPreview)
def preview_workspace_patch(
    payload: WorkspacePatchRequest,
    workspace: WorkspaceTools = Depends(get_workspace_tools),
    store: GenerationStore = Depends(get_generation_store),
) -> WorkspacePatchPreview:
    job = store.create_job(
        JobCreate(
            job_type=JobType.CODE,
            title=f"Preview patch {payload.path}",
            backend="workspace-patch",
            metadata={"path": payload.path, "create_if_missing": payload.create_if_missing},
        )
    )
    try:
        store.update_job_status(job.id, JobStatus.GENERATING, "Patch preview started", {"path": payload.path})
        preview = workspace.preview_patch(payload)
        final_job = store.update_job_status(
            job.id,
            JobStatus.COMPLETE,
            "Patch preview generated",
            {
                "path": preview.path,
                "exists": preview.exists,
                "additions": preview.additions,
                "deletions": preview.deletions,
                "risk_flags": preview.risk_flags,
                "current_sha256": preview.current_sha256,
                "proposed_sha256": preview.proposed_sha256,
            },
        )
        return preview.model_copy(update={"job": final_job})
    except WorkspaceAccessError as error:
        store.update_job_status(job.id, JobStatus.CANCELLED, str(error), {"path": payload.path})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except WorkspaceNotFoundError as error:
        store.update_job_status(job.id, JobStatus.CANCELLED, str(error), {"path": payload.path})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except WorkspaceUnsupportedFileError as error:
        store.update_job_status(job.id, JobStatus.CANCELLED, str(error), {"path": payload.path})
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(error)) from error
    except WorkspacePatchConflictError as error:
        store.update_job_status(job.id, JobStatus.CANCELLED, str(error), {"path": payload.path})
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/patches/apply", response_model=WorkspacePatchApplyResult)
def apply_workspace_patch(
    payload: WorkspacePatchApplyRequest,
    workspace: WorkspaceTools = Depends(get_workspace_tools),
    store: GenerationStore = Depends(get_generation_store),
) -> WorkspacePatchApplyResult:
    job = store.create_job(
        JobCreate(
            job_type=JobType.CODE,
            title=f"Apply patch {payload.path}",
            backend="workspace-patch",
            metadata={"path": payload.path, "approved": payload.approved},
        )
    )
    try:
        store.update_job_status(job.id, JobStatus.GENERATING, "Patch apply started", {"path": payload.path})
        result = workspace.apply_patch(payload)
        final_job = store.update_job_status(
            job.id,
            JobStatus.COMPLETE,
            "Patch applied",
            {
                "path": result.path,
                "additions": result.preview.additions,
                "deletions": result.preview.deletions,
                "risk_flags": result.preview.risk_flags,
                "proposed_sha256": result.preview.proposed_sha256,
            },
        )
        return result.model_copy(update={"job": final_job})
    except WorkspacePatchApprovalError as error:
        store.update_job_status(job.id, JobStatus.CANCELLED, str(error), {"path": payload.path})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except WorkspaceAccessError as error:
        store.update_job_status(job.id, JobStatus.CANCELLED, str(error), {"path": payload.path})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except WorkspaceNotFoundError as error:
        store.update_job_status(job.id, JobStatus.CANCELLED, str(error), {"path": payload.path})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except WorkspaceUnsupportedFileError as error:
        store.update_job_status(job.id, JobStatus.CANCELLED, str(error), {"path": payload.path})
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(error)) from error
    except WorkspacePatchConflictError as error:
        store.update_job_status(job.id, JobStatus.CANCELLED, str(error), {"path": payload.path})
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/commands/run", response_model=WorkspaceCommandRunResult)
def run_workspace_command(
    payload: WorkspaceCommandRunRequest,
    workspace: WorkspaceTools = Depends(get_workspace_tools),
    store: GenerationStore = Depends(get_generation_store),
) -> WorkspaceCommandRunResult:
    job = store.create_job(
        JobCreate(
            job_type=JobType.CODE,
            title=f"Run {payload.command}",
            backend="workspace-command",
            metadata={"command": payload.command, "cwd": payload.cwd},
        )
    )
    try:
        running_job = store.update_job_status(
            job.id,
            JobStatus.GENERATING,
            "Command execution started",
            {"command": payload.command, "cwd": payload.cwd},
        )
        result = workspace.run_command(payload, running_job)
        final_status = JobStatus.COMPLETE if result.status == "complete" else JobStatus.ERROR
        final_job = store.update_job_status(
            job.id,
            final_status,
            "Command execution completed" if result.status == "complete" else "Command execution failed",
            {
                "command": result.command,
                "cwd": result.cwd,
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "output_truncated": result.output_truncated,
            },
        )
        return result.model_copy(update={"job": final_job})
    except WorkspaceCommandApprovalError as error:
        store.update_job_status(job.id, JobStatus.CANCELLED, str(error), {"command": payload.command, "cwd": payload.cwd})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except WorkspaceCommandNotAllowedError as error:
        store.update_job_status(job.id, JobStatus.CANCELLED, str(error), {"command": payload.command, "cwd": payload.cwd})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except WorkspaceAccessError as error:
        store.update_job_status(job.id, JobStatus.CANCELLED, str(error), {"command": payload.command, "cwd": payload.cwd})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except WorkspaceNotFoundError as error:
        store.update_job_status(job.id, JobStatus.CANCELLED, str(error), {"command": payload.command, "cwd": payload.cwd})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
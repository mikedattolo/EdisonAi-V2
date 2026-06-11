from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from edison_core.api.dependencies import get_generation_store, get_model_gateway, get_workspace_project_manager
from edison_core.schemas import (
    JobCreate,
    JobStatus,
    JobType,
    WorkspaceProjectCreate,
    WorkspaceProjectRecord,
    WorkspaceRootRecord,
    WorkspaceEntry,
    WorkspaceFile,
    WorkspaceCommandRunRequest,
    WorkspaceCommandRunResult,
    WorkspaceInstallRequest,
    WorkspaceInstallResult,
    WorkspaceCopilotTaskRequest,
    WorkspaceCopilotTaskResult,
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
    EXCLUDED_NAMES,
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
from edison_core.services.model_gateway import ModelGateway
from edison_core.services.workspace_copilot import WorkspaceCopilot
from edison_core.services.workspace_projects import WorkspaceProjectManager


router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])


@router.get("/download")
def download_workspace(
    root_id: str = Query("app"),
    path: str = Query(""),
    projects: WorkspaceProjectManager = Depends(get_workspace_project_manager),
) -> StreamingResponse:
    """Download a workspace root (or a subfolder/file within it) as a .zip."""
    root = _workspace(root_id, projects).root
    base = (root / path).resolve() if path.strip() else root.resolve()
    try:
        base.relative_to(root.resolve())
    except ValueError as error:
        raise HTTPException(status_code=403, detail="Path is outside the workspace root.") from error
    if not base.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path or '.'}")

    top = base.name or root.name or "workspace"
    buffer = io.BytesIO()
    file_count = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        if base.is_file():
            archive.write(base, top)
            file_count = 1
        else:
            for current, dirnames, filenames in os.walk(base):
                dirnames[:] = [d for d in dirnames if d not in EXCLUDED_NAMES]
                for name in filenames:
                    if name in EXCLUDED_NAMES:
                        continue
                    file_path = Path(current) / name
                    if not file_path.is_file():
                        continue
                    try:
                        if file_path.stat().st_size > 50 * 1024 * 1024:
                            continue
                    except OSError:
                        continue
                    archive.write(file_path, f"{top}/{file_path.relative_to(base).as_posix()}")
                    file_count += 1
                    if file_count >= 8000:
                        break
                if file_count >= 8000:
                    break
    data = buffer.getvalue()
    return StreamingResponse(
        iter([data]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{top}.zip"',
            "Content-Length": str(len(data)),
        },
    )


@router.get("/roots", response_model=list[WorkspaceRootRecord])
def workspace_roots(
    projects: WorkspaceProjectManager = Depends(get_workspace_project_manager),
) -> list[WorkspaceRootRecord]:
    return projects.list_roots()


@router.post("/projects", response_model=WorkspaceProjectRecord, status_code=status.HTTP_201_CREATED)
def create_workspace_project(
    payload: WorkspaceProjectCreate,
    projects: WorkspaceProjectManager = Depends(get_workspace_project_manager),
) -> WorkspaceProjectRecord:
    try:
        return projects.create_project(payload)
    except WorkspaceAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error


@router.get("/summary", response_model=WorkspaceSummary)
def workspace_summary(
    root_id: str = Query("app"),
    projects: WorkspaceProjectManager = Depends(get_workspace_project_manager),
) -> WorkspaceSummary:
    return _workspace(root_id, projects).summarize()


@router.get("/scan", response_model=WorkspaceScan)
def workspace_scan(
    root_id: str = Query("app"),
    projects: WorkspaceProjectManager = Depends(get_workspace_project_manager),
) -> WorkspaceScan:
    return _workspace(root_id, projects).scan()


@router.post("/install", response_model=WorkspaceInstallResult)
def install_dependencies(
    payload: WorkspaceInstallRequest,
    projects: WorkspaceProjectManager = Depends(get_workspace_project_manager),
) -> WorkspaceInstallResult:
    try:
        return _workspace(payload.root_id, projects).install_dependencies(payload.package, payload.cwd)
    except WorkspaceCommandNotAllowedError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except WorkspaceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.get("/files", response_model=list[WorkspaceEntry])
def list_workspace_files(
    path: str = "",
    limit: int = Query(200, ge=1, le=500),
    root_id: str = Query("app"),
    projects: WorkspaceProjectManager = Depends(get_workspace_project_manager),
) -> list[WorkspaceEntry]:
    try:
        workspace = _workspace(root_id, projects)
        return workspace.list_directory(path, limit=limit)
    except WorkspaceAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except WorkspaceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.get("/files/content", response_model=WorkspaceFile)
def read_workspace_file(
    path: str = Query(..., min_length=1),
    root_id: str = Query("app"),
    projects: WorkspaceProjectManager = Depends(get_workspace_project_manager),
) -> WorkspaceFile:
    try:
        workspace = _workspace(root_id, projects)
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
    root_id: str = Query("app"),
    projects: WorkspaceProjectManager = Depends(get_workspace_project_manager),
) -> list[WorkspaceSearchMatch]:
    return _workspace(root_id, projects).search(payload)


@router.get("/instructions", response_model=list[WorkspaceInstructionFile])
def list_workspace_instructions(
    limit: int = Query(200, ge=1, le=500),
    root_id: str = Query("app"),
    projects: WorkspaceProjectManager = Depends(get_workspace_project_manager),
) -> list[WorkspaceInstructionFile]:
    return _workspace(root_id, projects).list_instruction_files(limit=limit)


@router.get("/instructions/context", response_model=WorkspaceInstructionContext)
def workspace_instruction_context(
    path: str = Query(..., min_length=1),
    root_id: str = Query("app"),
    projects: WorkspaceProjectManager = Depends(get_workspace_project_manager),
) -> WorkspaceInstructionContext:
    try:
        workspace = _workspace(root_id, projects)
        return workspace.instruction_context(path)
    except WorkspaceAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except WorkspaceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.get("/index/status", response_model=WorkspaceIndexStatus)
def workspace_index_status(
    root_id: str = Query("app"),
    projects: WorkspaceProjectManager = Depends(get_workspace_project_manager),
) -> WorkspaceIndexStatus:
    return _workspace(root_id, projects).index_status()


@router.post("/index/rebuild", response_model=WorkspaceIndexStatus)
def workspace_index_rebuild(
    root_id: str = Query("app"),
    projects: WorkspaceProjectManager = Depends(get_workspace_project_manager),
    store: GenerationStore = Depends(get_generation_store),
) -> WorkspaceIndexStatus:
    workspace = _workspace(root_id, projects)
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
    root_id: str = Query("app"),
    projects: WorkspaceProjectManager = Depends(get_workspace_project_manager),
) -> list[WorkspaceIndexSearchMatch]:
    return _workspace(root_id, projects).search_index(payload)


@router.post("/patches/preview", response_model=WorkspacePatchPreview)
def preview_workspace_patch(
    payload: WorkspacePatchRequest,
    root_id: str = Query("app"),
    projects: WorkspaceProjectManager = Depends(get_workspace_project_manager),
    store: GenerationStore = Depends(get_generation_store),
) -> WorkspacePatchPreview:
    workspace = _workspace(root_id, projects)
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
    root_id: str = Query("app"),
    projects: WorkspaceProjectManager = Depends(get_workspace_project_manager),
    store: GenerationStore = Depends(get_generation_store),
) -> WorkspacePatchApplyResult:
    workspace = _workspace(root_id, projects)
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
    root_id: str = Query("app"),
    projects: WorkspaceProjectManager = Depends(get_workspace_project_manager),
    store: GenerationStore = Depends(get_generation_store),
) -> WorkspaceCommandRunResult:
    workspace = _workspace(root_id, projects)
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


@router.post("/copilot/tasks", response_model=WorkspaceCopilotTaskResult, status_code=status.HTTP_201_CREATED)
def run_workspace_copilot_task(
    payload: WorkspaceCopilotTaskRequest,
    root_id: str = Query("app"),
    projects: WorkspaceProjectManager = Depends(get_workspace_project_manager),
    store: GenerationStore = Depends(get_generation_store),
    gateway: ModelGateway = Depends(get_model_gateway),
) -> WorkspaceCopilotTaskResult:
    workspace = _workspace(root_id, projects)
    job = store.create_job(
        JobCreate(
            job_type=JobType.CODE,
            title=f"Code Space task: {payload.instruction[:80]}",
            backend="workspace-copilot",
            metadata={
                "root_id": root_id,
                "preferred_model": payload.preferred_model,
                "auto_apply": payload.auto_apply,
                "run_commands": payload.run_commands,
            },
        )
    )
    try:
        return WorkspaceCopilot(workspace, gateway, store).run(payload, job)
    except WorkspaceAccessError as error:
        store.update_job_status(job.id, JobStatus.CANCELLED, str(error), {"root_id": root_id})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except WorkspaceNotFoundError as error:
        store.update_job_status(job.id, JobStatus.CANCELLED, str(error), {"root_id": root_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


def _workspace(root_id: str, projects: WorkspaceProjectManager) -> WorkspaceTools:
    try:
        return projects.workspace_for(root_id)
    except WorkspaceAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error

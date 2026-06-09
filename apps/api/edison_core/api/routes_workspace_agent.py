from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from edison_core.api.dependencies import (
    get_agent_run_coordinator,
    get_workspace_agent,
    get_workspace_project_manager,
)
from edison_core.schemas import (
    EdisonServiceRestartRequest,
    EdisonServiceRestartResult,
    WorkspaceAgentControlRequest,
    WorkspaceAgentControlResult,
    WorkspaceAgentStartRequest,
)
from edison_core.services.workspace_agent import AgentRunCoordinator, WorkspaceAgent
from edison_core.services.workspace_projects import WorkspaceProjectManager
from edison_core.services.workspace_tools import WorkspaceAccessError


router = APIRouter(prefix="/api/v1/workspace/agent", tags=["workspace-agent"])


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/stream")
def stream_agent(
    payload: WorkspaceAgentStartRequest,
    agent: WorkspaceAgent = Depends(get_workspace_agent),
    projects: WorkspaceProjectManager = Depends(get_workspace_project_manager),
) -> StreamingResponse:
    try:
        workspace = projects.workspace_for(payload.root_id)
    except WorkspaceAccessError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    def event_stream():
        try:
            for event, data in agent.stream(workspace, payload):
                yield _sse(event, data)
        except Exception as error:  # noqa: BLE001 - never break the stream contract
            yield _sse("error", {"detail": f"Stream failed: {error}"})
            yield _sse("done", {"status": "error", "summary": str(error), "changed_files": [], "steps": 0})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post("/control", response_model=WorkspaceAgentControlResult)
def control_agent(
    payload: WorkspaceAgentControlRequest,
    coordinator: AgentRunCoordinator = Depends(get_agent_run_coordinator),
) -> WorkspaceAgentControlResult:
    if payload.action == "stop":
        accepted = coordinator.cancel(payload.run_id)
        detail = "Stop signal sent." if accepted else "Run not found or already finished."
    else:
        accepted = coordinator.submit_decision(payload.run_id, payload.step_id, payload.action == "approve")
        detail = "Decision recorded." if accepted else "No pending command to decide on."
    return WorkspaceAgentControlResult(
        accepted=accepted,
        run_id=payload.run_id,
        action=payload.action,
        detail=detail,
    )


@router.post("/restart-edison", response_model=EdisonServiceRestartResult)
def restart_edison(payload: EdisonServiceRestartRequest) -> EdisonServiceRestartResult:
    units = [f"{name}.service" for name in payload.services] or ["edison-api.service", "edison-web.service"]
    env = os.environ.copy()
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")

    # Schedule the restart in a transient systemd unit so it survives edison-api being
    # killed during its own restart (a plain child would be in this service's cgroup).
    try:
        subprocess.run(
            ["systemd-run", "--user", "--collect", "--on-active=1", "systemctl", "--user", "restart", *units],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return EdisonServiceRestartResult(
            scheduled=True,
            services=units,
            detail="Edison is restarting; the UI will reconnect in a few seconds.",
        )
    except Exception:  # noqa: BLE001 - fall back to a detached shell
        try:
            subprocess.Popen(
                ["setsid", "bash", "-c", f"sleep 1; systemctl --user restart {' '.join(units)}"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return EdisonServiceRestartResult(
                scheduled=True,
                services=units,
                detail="Edison is restarting; the UI will reconnect in a few seconds.",
            )
        except Exception as error:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Could not schedule restart: {error}") from error

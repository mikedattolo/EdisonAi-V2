from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
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
def restart_edison(
    payload: EdisonServiceRestartRequest,
    projects: WorkspaceProjectManager = Depends(get_workspace_project_manager),
) -> EdisonServiceRestartResult:
    """Apply self-edits safely: rebuild the web app, verify the backend imports, then restart.

    edison-web serves a built dist/, so a rebuild is required for frontend edits to show.
    The backend is import-checked first so a broken edit never bricks the running API.
    """
    root = projects.app_root
    env = os.environ.copy()
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    notes: list[str] = []

    # 1. Rebuild the web app if requested (this also type-checks the frontend via tsc).
    web_build = "skipped"
    web_dir = root / "apps" / "web"
    if payload.build_web and web_dir.exists():
        try:
            completed = subprocess.run(
                ["npm", "run", "build"],
                cwd=web_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=420,
                check=False,
            )
            web_build = "ok" if completed.returncode == 0 else "failed"
            if completed.returncode != 0:
                notes.append("web build FAILED (web not restarted): " + (completed.stdout + completed.stderr).strip()[-600:])
        except Exception as error:  # noqa: BLE001
            web_build = "failed"
            notes.append(f"web build error: {error}")

    # 2. Verify the backend imports before restarting edison-api - never brick a running API.
    backend_ok = True
    python_bin = root / ".venv" / "bin" / "python"
    if not python_bin.exists():
        python_bin = Path(sys.executable)
    try:
        check_env = env.copy()
        check_env["PYTHONPATH"] = str(root / "apps" / "api")
        completed = subprocess.run(
            [str(python_bin), "-c", "import edison_core.main"],
            cwd=str(root),
            env=check_env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        backend_ok = completed.returncode == 0
        if not backend_ok:
            notes.append("backend import FAILED (api NOT restarted): " + completed.stderr.strip()[-600:])
    except Exception as error:  # noqa: BLE001
        backend_ok = False
        notes.append(f"backend check error: {error}")

    # 3. Restart only the services that are safe to restart.
    requested = [f"{name}.service" for name in payload.services] or ["edison-api.service", "edison-web.service"]
    units: list[str] = []
    for unit in requested:
        if unit == "edison-api.service" and not backend_ok:
            continue
        if unit == "edison-web.service" and web_build == "failed":
            continue
        units.append(unit)

    scheduled = False
    if units:
        # Run in a transient systemd unit so the restart survives edison-api being killed.
        try:
            subprocess.run(
                ["systemd-run", "--user", "--collect", "--on-active=1", "systemctl", "--user", "restart", *units],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            scheduled = True
        except Exception:  # noqa: BLE001
            try:
                subprocess.Popen(
                    ["setsid", "bash", "-c", f"sleep 1; systemctl --user restart {' '.join(units)}"],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                scheduled = True
            except Exception as error:  # noqa: BLE001
                notes.append(f"could not schedule restart: {error}")

    if not notes:
        detail = (
            f"Restarting {', '.join(units)}; the UI will reconnect in a few seconds."
            if scheduled
            else "Nothing to restart."
        )
    else:
        detail = " | ".join(notes)
        if scheduled:
            detail = f"Restarting {', '.join(units)}. " + detail

    return EdisonServiceRestartResult(
        scheduled=scheduled,
        services=units,
        web_build=web_build,
        backend_ok=backend_ok,
        detail=detail,
    )

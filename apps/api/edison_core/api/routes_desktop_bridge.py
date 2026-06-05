from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from edison_core.api.dependencies import get_desktop_bridge_client
from edison_core.schemas import DesktopBridgeActionRequest, DesktopBridgeActionResult, DesktopBridgeStatus
from edison_core.services.desktop_bridge import DesktopBridgeClient


router = APIRouter(prefix="/api/v1/desktop-bridge", tags=["desktop-bridge"])


@router.get("/status", response_model=DesktopBridgeStatus)
def desktop_bridge_status(
    bridge: DesktopBridgeClient = Depends(get_desktop_bridge_client),
) -> DesktopBridgeStatus:
    return bridge.status()


@router.get("/tools", response_model=DesktopBridgeActionResult)
def desktop_bridge_tools(
    bridge: DesktopBridgeClient = Depends(get_desktop_bridge_client),
) -> DesktopBridgeActionResult:
    return bridge.fetch("tools")


@router.get("/printers", response_model=DesktopBridgeActionResult)
def desktop_bridge_printers(
    bridge: DesktopBridgeClient = Depends(get_desktop_bridge_client),
) -> DesktopBridgeActionResult:
    return bridge.fetch("printers")


@router.post("/launch", response_model=DesktopBridgeActionResult)
def launch_desktop_tool(
    payload: DesktopBridgeActionRequest,
    bridge: DesktopBridgeClient = Depends(get_desktop_bridge_client),
) -> DesktopBridgeActionResult:
    return bridge.action("launch", {"tool_id": payload.tool_id, **payload.args})


@router.post("/notify", response_model=DesktopBridgeActionResult)
def desktop_notification(
    payload: DesktopBridgeActionRequest,
    bridge: DesktopBridgeClient = Depends(get_desktop_bridge_client),
) -> DesktopBridgeActionResult:
    return bridge.action("notify", {"tool_id": payload.tool_id, **payload.args})


@router.post("/labels/print", response_model=DesktopBridgeActionResult)
def print_label(
    payload: dict[str, Any],
    bridge: DesktopBridgeClient = Depends(get_desktop_bridge_client),
) -> DesktopBridgeActionResult:
    return bridge.action("print-label", payload)


@router.post("/files/list", response_model=DesktopBridgeActionResult)
def list_desktop_files(
    payload: dict[str, Any],
    bridge: DesktopBridgeClient = Depends(get_desktop_bridge_client),
) -> DesktopBridgeActionResult:
    return bridge.action("files/list", payload)


@router.post("/files/read", response_model=DesktopBridgeActionResult)
def read_desktop_file(
    payload: dict[str, Any],
    bridge: DesktopBridgeClient = Depends(get_desktop_bridge_client),
) -> DesktopBridgeActionResult:
    return bridge.action("files/read", payload)


@router.post("/files/write", response_model=DesktopBridgeActionResult)
def write_desktop_file(
    payload: dict[str, Any],
    bridge: DesktopBridgeClient = Depends(get_desktop_bridge_client),
) -> DesktopBridgeActionResult:
    return bridge.action("files/write", payload)


@router.post("/files/mkdir", response_model=DesktopBridgeActionResult)
def make_desktop_folder(
    payload: dict[str, Any],
    bridge: DesktopBridgeClient = Depends(get_desktop_bridge_client),
) -> DesktopBridgeActionResult:
    return bridge.action("files/mkdir", payload)


@router.post("/fusion/job", response_model=DesktopBridgeActionResult)
def queue_fusion_job(
    payload: dict[str, Any],
    bridge: DesktopBridgeClient = Depends(get_desktop_bridge_client),
) -> DesktopBridgeActionResult:
    return bridge.action("fusion/job", payload)


@router.post("/slicer/open", response_model=DesktopBridgeActionResult)
def open_slicer_model(
    payload: dict[str, Any],
    bridge: DesktopBridgeClient = Depends(get_desktop_bridge_client),
) -> DesktopBridgeActionResult:
    return bridge.action("slicer/open", payload)


@router.post("/slicer/prepare", response_model=DesktopBridgeActionResult)
def prepare_slicer_handoff(
    payload: dict[str, Any],
    bridge: DesktopBridgeClient = Depends(get_desktop_bridge_client),
) -> DesktopBridgeActionResult:
    return bridge.action("slicer/prepare", payload)


@router.post("/printers/register", response_model=DesktopBridgeActionResult)
def register_3d_printer(
    payload: dict[str, Any],
    bridge: DesktopBridgeClient = Depends(get_desktop_bridge_client),
) -> DesktopBridgeActionResult:
    return bridge.action("printers/register", payload)

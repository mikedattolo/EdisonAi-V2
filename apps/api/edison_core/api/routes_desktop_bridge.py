from __future__ import annotations

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

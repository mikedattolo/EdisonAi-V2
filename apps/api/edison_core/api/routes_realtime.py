from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from edison_core.api.dependencies import get_realtime_service
from edison_core.services.realtime import RealtimeService


router = APIRouter(prefix="/api/v1/realtime", tags=["realtime"])


@router.get("/context")
def realtime_context(
    latitude: float | None = Query(None),
    longitude: float | None = Query(None),
    realtime: RealtimeService = Depends(get_realtime_service),
) -> dict[str, Any]:
    """Current location (IP-based or client lat/lon), local time, and weather."""
    return realtime.context(latitude=latitude, longitude=longitude)

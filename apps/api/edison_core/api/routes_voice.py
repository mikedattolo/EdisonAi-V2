from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from edison_core.api.dependencies import get_voice_bridge_service
from edison_core.schemas import VoiceCommandRequest, VoiceEvent, VoiceStatus
from edison_core.services.voice_bridge import VoiceBridgeService

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])


@router.post("/brio", response_model=VoiceEvent)
def brio_command(
    payload: VoiceCommandRequest,
    service: VoiceBridgeService = Depends(get_voice_bridge_service),
) -> VoiceEvent:
    return service.handle_command(payload.transcript, payload.source)


@router.post("/heartbeat")
def heartbeat(service: VoiceBridgeService = Depends(get_voice_bridge_service)) -> dict:
    service.ping()
    return {"ok": True}


@router.get("/events", response_model=list[VoiceEvent])
def events(
    after: int = Query(0),
    service: VoiceBridgeService = Depends(get_voice_bridge_service),
) -> list[VoiceEvent]:
    return service.events_after(after)


@router.get("/status", response_model=VoiceStatus)
def status(service: VoiceBridgeService = Depends(get_voice_bridge_service)) -> VoiceStatus:
    return service.status()

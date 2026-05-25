from __future__ import annotations

from fastapi import APIRouter, Depends

from edison_core.api.dependencies import get_session_state_store
from edison_core.schemas import SessionStateRecord, SessionStateUpdate
from edison_core.services.session_state import SessionStateStore


router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.get("/{session_id}", response_model=SessionStateRecord)
def get_session_state(
    session_id: str,
    store: SessionStateStore = Depends(get_session_state_store),
) -> SessionStateRecord:
    return store.get_or_create(session_id)


@router.put("/{session_id}", response_model=SessionStateRecord)
def update_session_state(
    session_id: str,
    payload: SessionStateUpdate,
    store: SessionStateStore = Depends(get_session_state_store),
) -> SessionStateRecord:
    return store.update(session_id, payload)
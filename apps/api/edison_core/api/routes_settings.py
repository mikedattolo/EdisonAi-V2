from __future__ import annotations

from fastapi import APIRouter, Depends

from edison_core.api.dependencies import get_runtime_settings_store
from edison_core.schemas import RuntimeSettingsRecord, RuntimeSettingsUpdate
from edison_core.services.runtime_settings import RuntimeSettingsStore


router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("/runtime", response_model=RuntimeSettingsRecord)
def get_runtime_settings(
    store: RuntimeSettingsStore = Depends(get_runtime_settings_store),
) -> RuntimeSettingsRecord:
    return store.get()


@router.put("/runtime", response_model=RuntimeSettingsRecord)
def update_runtime_settings(
    payload: RuntimeSettingsUpdate,
    store: RuntimeSettingsStore = Depends(get_runtime_settings_store),
) -> RuntimeSettingsRecord:
    return store.update(payload)

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from edison_core.api.dependencies import get_model_registry, get_model_router
from edison_core.schemas import ChatMode, ModelProfile, ModelSelection
from edison_core.services.model_registry import ModelRegistry, ModelRouter, ModelSelectionError


router = APIRouter(prefix="/api/v1/models", tags=["models"])


@router.get("", response_model=list[ModelProfile])
def list_models(registry: ModelRegistry = Depends(get_model_registry)) -> list[ModelProfile]:
    return registry.list_profiles()


@router.get("/select", response_model=ModelSelection)
def select_model(
    mode: ChatMode = Query(ChatMode.CHAT),
    preferred_model: str | None = None,
    router_service: ModelRouter = Depends(get_model_router),
) -> ModelSelection:
    try:
        return router_service.select_model(mode=mode, preferred_model=preferred_model)
    except ModelSelectionError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
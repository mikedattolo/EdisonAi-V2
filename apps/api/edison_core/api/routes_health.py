from __future__ import annotations

from fastapi import APIRouter, Depends

from edison_core.api.dependencies import get_fan_control_service, get_status_service
from edison_core.schemas import (
    GPUFanControlSnapshot,
    GPUFanControlState,
    GPUFanControlUpdate,
    HealthResponse,
    SystemStatus,
)
from edison_core.services.system_status import GPUFanControlService, SystemStatusService


router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(service="edison-core-api", version="0.1.0")


@router.get("/api/v1/status", response_model=SystemStatus)
def system_status(
    status_service: SystemStatusService = Depends(get_status_service),
) -> SystemStatus:
    return status_service.snapshot()


@router.get("/api/v1/system/fans", response_model=GPUFanControlSnapshot)
def gpu_fan_controls(
    fan_control_service: GPUFanControlService = Depends(get_fan_control_service),
) -> GPUFanControlSnapshot:
    return fan_control_service.snapshot()


@router.put("/api/v1/system/fans/{gpu_index}", response_model=GPUFanControlState)
def update_gpu_fan_control(
    gpu_index: int,
    payload: GPUFanControlUpdate,
    fan_control_service: GPUFanControlService = Depends(get_fan_control_service),
) -> GPUFanControlState:
    return fan_control_service.update_policy(gpu_index, payload)
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from edison_core.api.dependencies import get_generation_store, get_hardware_device_service
from edison_core.schemas import (
    ArtifactCreate,
    ArtifactKind,
    CameraDeviceRecord,
    CameraSnapshotRequest,
    CameraSnapshotResponse,
    HardwareAcceleratorRecord,
    HardwareStatus,
)
from edison_core.services.generation_store import GenerationStore
from edison_core.services.hardware_devices import CameraCaptureError, HardwareDeviceService


router = APIRouter(prefix="/api/v1/hardware", tags=["hardware"])


@router.get("/status", response_model=HardwareStatus)
def hardware_status(
    hardware: HardwareDeviceService = Depends(get_hardware_device_service),
) -> HardwareStatus:
    return hardware.snapshot()


@router.get("/accelerators", response_model=list[HardwareAcceleratorRecord])
def hardware_accelerators(
    hardware: HardwareDeviceService = Depends(get_hardware_device_service),
) -> list[HardwareAcceleratorRecord]:
    return hardware.detect_accelerators()


@router.get("/cameras", response_model=list[CameraDeviceRecord])
def hardware_cameras(
    hardware: HardwareDeviceService = Depends(get_hardware_device_service),
) -> list[CameraDeviceRecord]:
    return hardware.detect_cameras()


@router.post("/cameras/snapshot", response_model=CameraSnapshotResponse, status_code=status.HTTP_201_CREATED)
def capture_camera_snapshot(
    payload: CameraSnapshotRequest,
    hardware: HardwareDeviceService = Depends(get_hardware_device_service),
    store: GenerationStore = Depends(get_generation_store),
) -> CameraSnapshotResponse:
    try:
        capture = hardware.capture_camera_snapshot(payload)
    except CameraCaptureError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    artifact = store.create_artifact(
        ArtifactCreate(
            kind=ArtifactKind.IMAGE,
            title=payload.title or "Brio camera snapshot",
            path=capture.artifact_path,
            mime_type="image/jpeg",
            metadata={
                "source": "camera",
                "camera": capture.camera.model_dump(mode="json"),
                "absolute_path": str(capture.absolute_path),
            },
        )
    )
    return CameraSnapshotResponse(camera=capture.camera, artifact=artifact, detail=capture.detail)

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from starlette.background import BackgroundTask
from fastapi.responses import StreamingResponse

from edison_core.api.dependencies import get_generation_store, get_hardware_device_service
from edison_core.schemas import (
    ArtifactCreate,
    ArtifactKind,
    CameraDeviceRecord,
    CameraSnapshotRequest,
    CameraSnapshotResponse,
    CameraVisionStatus,
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


@router.get("/cameras/feed")
def camera_feed(
    device_path: str | None = Query(None),
    width: int = Query(1280, ge=160, le=4096),
    height: int = Query(720, ge=120, le=2160),
    input_format: Literal["mjpeg", "yuyv422"] = Query("mjpeg"),
    hardware: HardwareDeviceService = Depends(get_hardware_device_service),
) -> StreamingResponse:
    payload = CameraSnapshotRequest(
        device_path=device_path,
        width=width,
        height=height,
        input_format=input_format,
    )
    try:
        _camera, command, boundary = hardware.camera_feed_command(payload)
    except CameraCaptureError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return StreamingResponse(
        _stream_process(process),
        media_type=f"multipart/x-mixed-replace; boundary={boundary}",
        background=BackgroundTask(_terminate_process, process),
    )


@router.get("/cameras/vision", response_model=CameraVisionStatus)
def camera_vision_status(
    device_path: str | None = Query(None),
    hardware: HardwareDeviceService = Depends(get_hardware_device_service),
) -> CameraVisionStatus:
    return hardware.camera_vision_status(device_path)


def _stream_process(process: subprocess.Popen[bytes]) -> Iterator[bytes]:
    try:
        if process.stdout is None:
            return
        while True:
            chunk = process.stdout.read(32_768)
            if not chunk:
                break
            yield chunk
    finally:
        _terminate_process(process)


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from starlette.background import BackgroundTask
from fastapi.responses import StreamingResponse

from edison_core.api.dependencies import get_generation_store, get_hardware_device_service, get_model_gateway
from edison_core.schemas import (
    ArtifactCreate,
    ArtifactKind,
    ArtifactRecord,
    CameraAnalyzeRequest,
    CameraDeviceRecord,
    CameraFrameAnalysisResponse,
    CameraSnapshotRequest,
    CameraSnapshotResponse,
    CameraVisionStatus,
    HardwareAcceleratorRecord,
    HardwareStatus,
)
from edison_core.services.generation_store import GenerationStore
from edison_core.services.hardware_devices import CameraCaptureError, CapturedCameraSnapshot, HardwareDeviceService
from edison_core.services.model_gateway import ModelGateway


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

    artifact = _save_camera_artifact(store, capture, payload.title or "Brio camera snapshot", {})
    return CameraSnapshotResponse(camera=capture.camera, artifact=artifact, detail=capture.detail)


@router.post("/cameras/analyze", response_model=CameraFrameAnalysisResponse, status_code=status.HTTP_201_CREATED)
def analyze_camera_frame(
    payload: CameraAnalyzeRequest,
    hardware: HardwareDeviceService = Depends(get_hardware_device_service),
    store: GenerationStore = Depends(get_generation_store),
    gateway: ModelGateway = Depends(get_model_gateway),
) -> CameraFrameAnalysisResponse:
    try:
        capture = hardware.capture_camera_snapshot(payload)
    except CameraCaptureError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    artifact = _save_camera_artifact(
        store,
        capture,
        payload.title or "Brio camera AI frame",
        {"analysis_prompt": payload.prompt},
    )
    image_bytes = capture.absolute_path.read_bytes()
    selection, inference = gateway.analyze_image(payload.prompt, image_bytes, "image/jpeg")
    vision_status = hardware.camera_vision_status(payload.device_path)
    response_status = "complete" if inference.finish_reason in {"stop", "length"} else (
        "setup_required" if inference.finish_reason == "not_configured" else "error"
    )
    summary = inference.content
    if response_status == "setup_required":
        summary = (
            "I captured the frame and saved it in Edison, but local vision analysis still needs a ready VLM endpoint. "
            f"{inference.content}"
        )
    return CameraFrameAnalysisResponse(
        status=response_status,
        camera=capture.camera,
        artifact=artifact,
        summary=summary,
        model_id=inference.model_id,
        backend="local-vision",
        detections=_extract_detection_labels(inference.content),
        detail=vision_status.detail,
        metadata={
            "vision_status": vision_status.model_dump(mode="json"),
            "model_selection": selection.model_dump(mode="json"),
            "gateway": inference.metadata,
        },
    )


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


def _save_camera_artifact(
    store: GenerationStore,
    capture: CapturedCameraSnapshot,
    title: str,
    metadata: dict,
) -> ArtifactRecord:
    return store.create_artifact(
        ArtifactCreate(
            kind=ArtifactKind.IMAGE,
            title=title,
            path=capture.artifact_path,
            mime_type="image/jpeg",
            metadata={
                "source": "camera",
                "camera": capture.camera.model_dump(mode="json"),
                "absolute_path": str(capture.absolute_path),
                **metadata,
            },
        )
    )


def _extract_detection_labels(content: str) -> list[str]:
    labels: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip(" -•\t")
        if not line or len(line) > 80:
            continue
        lowered = line.lower()
        if any(
            word in lowered
            for word in (
                "object",
                "person",
                "screen",
                "monitor",
                "camera",
                "desk",
                "tool",
                "chair",
                "door",
                "computer",
                "keyboard",
                "workbench",
            )
        ):
            labels.append(line.rstrip("."))
        if len(labels) >= 8:
            break
    return labels


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

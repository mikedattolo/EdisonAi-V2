from __future__ import annotations

from edison_core.config import load_settings
from edison_core.database import SQLiteDatabase
from edison_core.mcp.runtime import MCPServer, MCPTool, integer_schema, object_schema, string_schema
from edison_core.schemas import (
    ArtifactCreate,
    ArtifactKind,
    CameraAnalyzeRequest,
    CameraFrameAnalysisResponse,
    CameraSnapshotRequest,
    CameraSnapshotResponse,
)
from edison_core.services.generation_store import GenerationStore
from edison_core.services.hardware_devices import CameraCaptureError, CapturedCameraSnapshot, HardwareDeviceService
from edison_core.services.model_gateway import ModelGateway
from edison_core.services.model_registry import ModelRegistry, ModelRouter


def create_server(
    hardware: HardwareDeviceService | None = None,
    store: GenerationStore | None = None,
    gateway: ModelGateway | None = None,
) -> MCPServer:
    devices = hardware or _default_hardware()
    media_store = store or _default_store()
    vision_gateway = gateway or _default_gateway()

    return MCPServer(
        name="edison-camera",
        version="0.1.0",
        tools=[
            MCPTool(
                name="camera.status",
                description="Return detected Edison camera devices and capture readiness.",
                input_schema=object_schema(),
                handler=lambda _: devices.detect_cameras(),
            ),
            MCPTool(
                name="camera.vision_status",
                description="Return live feed and Hailo/local vision readiness for a camera.",
                input_schema=object_schema({"device_path": string_schema("Optional /dev/video* path", "")}),
                handler=lambda args: devices.camera_vision_status(_optional_string(args.get("device_path"))),
            ),
            MCPTool(
                name="camera.snapshot",
                description="Capture one camera frame and save it as an Edison artifact.",
                input_schema=_camera_capture_schema(title_description="Artifact title"),
                handler=lambda args: _snapshot(args, devices, media_store),
            ),
            MCPTool(
                name="camera.analyze_frame",
                description="Capture one camera frame, analyze it with the configured local VLM, and save the frame artifact.",
                input_schema=_camera_capture_schema(
                    title_description="Artifact title",
                    extra={
                        "prompt": string_schema(
                            "Vision prompt",
                            "Describe the visible scene, important objects, people, screens, and anything Edison should pay attention to.",
                        )
                    },
                ),
                handler=lambda args: _analyze(args, devices, media_store, vision_gateway),
            ),
        ],
    )


def _snapshot(args: dict, hardware: HardwareDeviceService, store: GenerationStore) -> CameraSnapshotResponse:
    try:
        payload = _snapshot_request(args)
        capture = hardware.capture_camera_snapshot(payload)
    except CameraCaptureError as error:
        raise ValueError(str(error)) from error
    artifact = _save_camera_artifact(store, capture, payload.title or "Brio camera snapshot", {})
    return CameraSnapshotResponse(camera=capture.camera, artifact=artifact, detail=capture.detail)


def _analyze(
    args: dict,
    hardware: HardwareDeviceService,
    store: GenerationStore,
    gateway: ModelGateway,
) -> CameraFrameAnalysisResponse:
    try:
        payload = CameraAnalyzeRequest(**_snapshot_payload(args), prompt=str(args.get("prompt") or "Describe this camera frame."))
        capture = hardware.capture_camera_snapshot(payload)
    except CameraCaptureError as error:
        raise ValueError(str(error)) from error

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


def _camera_capture_schema(title_description: str, extra: dict | None = None) -> dict:
    properties = {
        "device_path": string_schema("Optional /dev/video* path", ""),
        "width": integer_schema("Frame width", 1280, 160, 4096),
        "height": integer_schema("Frame height", 720, 120, 2160),
        "input_format": string_schema("Camera input format: mjpeg or yuyv422", "mjpeg"),
        "title": string_schema(title_description, ""),
        **(extra or {}),
    }
    return object_schema(properties)


def _snapshot_request(args: dict) -> CameraSnapshotRequest:
    return CameraSnapshotRequest(**_snapshot_payload(args))


def _snapshot_payload(args: dict) -> dict:
    return {
        "device_path": _optional_string(args.get("device_path")),
        "width": int(args.get("width", 1280)),
        "height": int(args.get("height", 720)),
        "input_format": str(args.get("input_format") or "mjpeg"),
        "title": _optional_string(args.get("title")),
    }


def _save_camera_artifact(
    store: GenerationStore,
    capture: CapturedCameraSnapshot,
    title: str,
    metadata: dict,
):
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
    known_labels = (
        ("person", "person"),
        ("people", "people"),
        ("monitor", "monitor"),
        ("screen", "screen"),
        ("camera", "camera"),
        ("desk", "desk"),
        ("tool", "tools"),
        ("printer", "printer"),
        ("computer", "computer"),
        ("keyboard", "keyboard"),
        ("package", "package"),
        ("product", "product"),
    )
    lowered_content = content.lower()
    labels: list[str] = []
    for needle, label in known_labels:
        if needle in lowered_content and label not in labels:
            labels.append(label)
        if len(labels) >= 8:
            break
    return labels


def _optional_string(value) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _default_hardware() -> HardwareDeviceService:
    return HardwareDeviceService(load_settings())


def _default_store() -> GenerationStore:
    settings = load_settings()
    store = GenerationStore(SQLiteDatabase(settings.database_path))
    store.initialize()
    return store


def _default_gateway() -> ModelGateway:
    settings = load_settings()
    registry = ModelRegistry.from_file(settings.model_registry_path)
    return ModelGateway(ModelRouter(registry))


def main() -> None:
    create_server().serve_stdio()


if __name__ == "__main__":
    main()

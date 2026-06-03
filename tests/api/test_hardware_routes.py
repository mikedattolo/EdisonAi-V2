from pathlib import Path

from fastapi.testclient import TestClient

from edison_core.config import EdisonSettings
from edison_core.main import create_app
from edison_core.schemas import (
    CameraDeviceRecord,
    CameraSnapshotRequest,
    CameraVisionStatus,
    HardwareAcceleratorRecord,
    HardwareStatus,
)
from edison_core.services.hardware_devices import CapturedCameraSnapshot


def test_hardware_status_route_reports_accelerator_and_camera(tmp_path):
    app = create_app(_settings(tmp_path))
    app.state.hardware_device_service = _FakeHardwareDeviceService(tmp_path / "artifacts")
    client = TestClient(app)

    response = client.get("/api/v1/hardware/status")

    body = response.json()
    assert response.status_code == 200
    assert body["accelerators"][0]["kind"] == "hailo8"
    assert body["accelerators"][0]["status"] == "runtime_missing"
    assert body["cameras"][0]["id"] == "logitech-brio"
    assert body["cameras"][0]["capture_path"] == "/dev/video0"


def test_camera_snapshot_route_creates_downloadable_artifact(tmp_path):
    app = create_app(_settings(tmp_path))
    app.state.hardware_device_service = _FakeHardwareDeviceService(tmp_path / "artifacts")
    client = TestClient(app)

    created = client.post(
        "/api/v1/hardware/cameras/snapshot",
        json={"device_path": "/dev/video0", "width": 1280, "height": 720, "input_format": "mjpeg"},
    )
    artifact_id = created.json()["artifact"]["id"]
    downloaded = client.get(f"/api/v1/artifacts/{artifact_id}/download")

    assert created.status_code == 201
    assert created.json()["artifact"]["kind"] == "image"
    assert created.json()["camera"]["id"] == "logitech-brio"
    assert downloaded.status_code == 200
    assert downloaded.content.startswith(b"\xff\xd8")


def test_camera_vision_route_reports_setup_state(tmp_path):
    app = create_app(_settings(tmp_path))
    app.state.hardware_device_service = _FakeHardwareDeviceService(tmp_path / "artifacts")
    client = TestClient(app)

    response = client.get("/api/v1/hardware/cameras/vision")

    assert response.status_code == 200
    assert response.json()["status"] == "setup_required"
    assert response.json()["camera"]["id"] == "logitech-brio"
    assert response.json()["backend"] == "hailo8"


class _FakeHardwareDeviceService:
    def __init__(self, artifact_root: Path) -> None:
        self.artifact_root = artifact_root

    def snapshot(self) -> HardwareStatus:
        return HardwareStatus(
            accelerators=self.detect_accelerators(),
            cameras=self.detect_cameras(),
        )

    def detect_accelerators(self) -> list[HardwareAcceleratorRecord]:
        return [
            HardwareAcceleratorRecord(
                id="hailo8",
                name="Hailo-8 AI Accelerator",
                kind="hailo8",
                bus="pcie",
                status="runtime_missing",
                detail="Hailo-8 is present; HailoRT is missing.",
                pci_address="0a:00.0",
                vendor_id="1e60",
                product_id="2864",
            )
        ]

    def detect_cameras(self) -> list[CameraDeviceRecord]:
        return [
            CameraDeviceRecord(
                id="logitech-brio",
                name="Logitech BRIO Ultra HD Webcam",
                status="ready",
                detail="Brio is capture-capable.",
                vendor_id="046d",
                product_id="085e",
                device_paths=["/dev/video0", "/dev/video1"],
                media_paths=["/dev/media0"],
                capture_path="/dev/video0",
                formats=["MJPG 1280x720"],
            )
        ]

    def capture_camera_snapshot(self, payload: CameraSnapshotRequest) -> CapturedCameraSnapshot:
        output_dir = self.artifact_root / "camera"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "fake-brio.jpg"
        output_path.write_bytes(b"\xff\xd8\xff\xd9")
        return CapturedCameraSnapshot(
            camera=self.detect_cameras()[0],
            absolute_path=output_path,
            artifact_path="camera/fake-brio.jpg",
            detail=f"Captured fake frame from {payload.device_path}.",
        )

    def camera_vision_status(self, device_path: str | None = None) -> CameraVisionStatus:
        return CameraVisionStatus(
            status="setup_required",
            camera=self.detect_cameras()[0],
            backend="hailo8",
            feed_url="/api/v1/hardware/cameras/feed",
            detail="Camera feed is ready, but HailoRT is missing.",
        )


def _settings(tmp_path: Path) -> EdisonSettings:
    return EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        artifact_root=tmp_path / "artifacts",
        log_root=tmp_path / "logs",
        workspace_roots=[tmp_path],
    )

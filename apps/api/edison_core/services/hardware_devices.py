from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from edison_core.config import EdisonSettings
from edison_core.schemas import (
    CameraDeviceRecord,
    CameraSnapshotRequest,
    HardwareAcceleratorRecord,
    HardwareStatus,
)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class CapturedCameraSnapshot:
    camera: CameraDeviceRecord
    absolute_path: Path
    artifact_path: str
    detail: str


CommandRunner = Callable[[list[str], float], CommandResult]


class HardwareDeviceService:
    def __init__(self, settings: EdisonSettings, runner: CommandRunner | None = None) -> None:
        self.settings = settings
        self._runner = runner or _run_command

    def snapshot(self) -> HardwareStatus:
        return HardwareStatus(
            accelerators=self.detect_accelerators(),
            cameras=self.detect_cameras(),
        )

    def detect_accelerators(self) -> list[HardwareAcceleratorRecord]:
        return [self._detect_hailo8()]

    def detect_cameras(self) -> list[CameraDeviceRecord]:
        cameras = self._parse_v4l2_cameras()
        if cameras:
            return cameras
        return self._fallback_camera_devices()

    def capture_camera_snapshot(self, payload: CameraSnapshotRequest) -> CapturedCameraSnapshot:
        cameras = self.detect_cameras()
        ready_cameras = [camera for camera in cameras if camera.capture_path]
        if not ready_cameras:
            raise CameraCaptureError("No capture-capable camera was detected.")

        device_path = payload.device_path or ready_cameras[0].capture_path
        if not device_path or not _is_video_device_path(device_path):
            raise CameraCaptureError("Camera device path must be a /dev/video* device.")

        selected = next(
            (camera for camera in ready_cameras if device_path in camera.device_paths),
            None,
        )
        if selected is None:
            raise CameraCaptureError(f"Camera device is not managed by Edison: {device_path}")

        snapshot_dir = self.settings.artifact_root / "camera"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        output_name = f"brio-snapshot-{timestamp}.jpg"
        output_path = snapshot_dir / output_name
        size = f"{payload.width}x{payload.height}"
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "v4l2",
            "-input_format",
            payload.input_format,
            "-video_size",
            size,
            "-i",
            device_path,
            "-frames:v",
            "1",
            str(output_path),
        ]
        result = self._runner(command, 15.0)
        if result.returncode != 0 or not output_path.exists():
            detail = result.stderr.strip() or result.stdout.strip() or "Camera snapshot failed."
            raise CameraCaptureError(detail)
        return CapturedCameraSnapshot(
            camera=selected,
            absolute_path=output_path,
            artifact_path=f"camera/{output_name}",
            detail=f"Captured {size} {payload.input_format} frame from {device_path}.",
        )

    def _detect_hailo8(self) -> HardwareAcceleratorRecord:
        lspci = self._runner(["lspci", "-nn"], 2.0)
        pci_line = _first_matching_line(lspci.stdout, ("Hailo", "1e60:2864"))
        packages = _matching_lines(self._run_if_available(["dpkg", "-l"], 2.0).stdout, ("hailo", "hailort"))
        runtime_path = shutil.which("hailortcli")
        runtime_version = self._hailort_version(runtime_path)
        device_nodes = [str(path) for path in sorted(Path("/dev").glob("hailo*"))]
        lsmod = self._run_if_available(["lsmod"], 2.0)
        driver_loaded = bool(device_nodes) or "hailo" in lsmod.stdout.lower()

        if not pci_line:
            return HardwareAcceleratorRecord(
                id="hailo8",
                name="Hailo-8 AI Accelerator",
                kind="hailo8",
                bus="pcie",
                status="not_detected",
                detail="No Hailo-8 PCIe device was detected by lspci.",
                metadata={"packages": packages},
            )

        pci_address, vendor_id, product_id = _parse_pci_identity(pci_line)
        if not driver_loaded:
            status = "driver_missing"
            detail = "Hailo-8 is visible on PCIe, but the Hailo PCIe driver is not loaded."
        elif not runtime_path:
            status = "runtime_missing"
            detail = "Hailo driver appears present, but hailortcli is not installed."
        else:
            identify = self._runner(["hailortcli", "fw-control", "identify"], 5.0)
            if identify.returncode == 0:
                status = "ready"
                detail = "HailoRT can communicate with the Hailo-8 accelerator."
            else:
                status = "error"
                detail = identify.stderr.strip() or identify.stdout.strip() or "hailortcli identify failed."

        return HardwareAcceleratorRecord(
            id="hailo8",
            name="Hailo-8 AI Accelerator",
            kind="hailo8",
            bus="pcie",
            status=status,
            detail=detail,
            pci_address=pci_address,
            vendor_id=vendor_id,
            product_id=product_id,
            device_nodes=device_nodes,
            driver_loaded=driver_loaded,
            runtime_available=bool(runtime_path),
            runtime_version=runtime_version,
            metadata={
                "pci_line": pci_line,
                "runtime_path": runtime_path,
                "packages": packages,
            },
        )

    def _hailort_version(self, runtime_path: str | None) -> str | None:
        if not runtime_path:
            return None
        result = self._runner([runtime_path, "--version"], 2.0)
        if result.returncode != 0:
            return None
        return (result.stdout.strip() or result.stderr.strip()).splitlines()[0]

    def _parse_v4l2_cameras(self) -> list[CameraDeviceRecord]:
        listed = self._run_if_available(["v4l2-ctl", "--list-devices"], 2.0)
        if listed.returncode != 0 or not listed.stdout.strip():
            return []

        usb = self._run_if_available(["lsusb"], 2.0).stdout
        cameras: list[CameraDeviceRecord] = []
        for index, (name, paths) in enumerate(_parse_v4l2_blocks(listed.stdout)):
            device_paths = [path for path in paths if path.startswith("/dev/video")]
            media_paths = [path for path in paths if path.startswith("/dev/media")]
            formats: list[str] = []
            capture_path: str | None = None
            permission_denied = False
            for device_path in device_paths:
                capability = self._run_if_available(["v4l2-ctl", "--device", device_path, "--all"], 2.0)
                text = f"{capability.stdout}\n{capability.stderr}"
                if "Permission denied" in text:
                    permission_denied = True
                if "Video Capture" in text and capture_path is None:
                    capture_path = device_path
                if "Video Capture" in text:
                    formats.extend(self._camera_formats(device_path))

            vendor_id, product_id = _camera_usb_ids(name, usb)
            is_brio = vendor_id == "046d" and product_id == "085e"
            if capture_path:
                status = "ready"
                detail = f"{name} is capture-capable at {capture_path}."
            elif permission_denied:
                status = "permission_required"
                detail = f"{name} was detected, but Edison cannot read its video nodes."
            else:
                status = "detected"
                detail = f"{name} was detected, but no capture stream was identified."
            cameras.append(
                CameraDeviceRecord(
                    id="logitech-brio" if is_brio else f"camera-{index}",
                    name="Logitech BRIO Ultra HD Webcam" if is_brio else name,
                    status=status,
                    detail=detail,
                    vendor_id=vendor_id,
                    product_id=product_id,
                    device_paths=device_paths,
                    media_paths=media_paths,
                    capture_path=capture_path,
                    formats=_unique(formats)[:24],
                    metadata={"raw_name": name},
                )
            )
        return cameras

    def _fallback_camera_devices(self) -> list[CameraDeviceRecord]:
        video_nodes = [str(path) for path in sorted(Path("/dev").glob("video*"))]
        media_nodes = [str(path) for path in sorted(Path("/dev").glob("media*"))]
        usb = self._run_if_available(["lsusb"], 2.0).stdout
        vendor_id, product_id = _camera_usb_ids("Logitech BRIO", usb)
        if not video_nodes and "046d:085e" not in usb:
            return []
        name = "Logitech BRIO Ultra HD Webcam" if "046d:085e" in usb else "USB Camera"
        return [
            CameraDeviceRecord(
                id="logitech-brio" if "046d:085e" in usb else "camera-0",
                name=name,
                status="detected",
                detail="Camera device nodes are present, but v4l2-ctl is not available for capability probing.",
                vendor_id=vendor_id,
                product_id=product_id,
                device_paths=video_nodes,
                media_paths=media_nodes,
                capture_path=video_nodes[0] if video_nodes else None,
                metadata={"probe": "fallback"},
            )
        ]

    def _camera_formats(self, device_path: str) -> list[str]:
        result = self._run_if_available(["v4l2-ctl", "--device", device_path, "--list-formats-ext"], 2.0)
        if result.returncode != 0:
            return []
        formats: list[str] = []
        active_format: str | None = None
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            match = re.match(r"\[\d+\]: '([^']+)' \((.+)\)", line)
            if match:
                active_format = f"{match.group(1)} ({match.group(2)})"
                formats.append(active_format)
                continue
            size_match = re.match(r"Size: Discrete (\d+x\d+)", line)
            if size_match and active_format:
                formats.append(f"{active_format} {size_match.group(1)}")
        return formats

    def _run_if_available(self, command: list[str], timeout: float) -> CommandResult:
        if shutil.which(command[0]) is None:
            return CommandResult(returncode=127, stderr=f"{command[0]} is not installed")
        return self._runner(command, timeout)


class CameraCaptureError(RuntimeError):
    pass


def _run_command(command: list[str], timeout: float) -> CommandResult:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        return CommandResult(returncode=127, stderr=str(error))
    return CommandResult(result.returncode, result.stdout, result.stderr)


def _parse_v4l2_blocks(output: str) -> list[tuple[str, list[str]]]:
    blocks: list[tuple[str, list[str]]] = []
    current_name: str | None = None
    current_paths: list[str] = []
    for line in output.splitlines():
        if not line.strip():
            if current_name:
                blocks.append((current_name, current_paths))
            current_name = None
            current_paths = []
            continue
        if not line.startswith((" ", "\t")):
            if current_name:
                blocks.append((current_name, current_paths))
            current_name = line.rstrip(":")
            current_paths = []
            continue
        path = line.strip()
        if path.startswith("/dev/"):
            current_paths.append(path)
    if current_name:
        blocks.append((current_name, current_paths))
    return blocks


def _first_matching_line(output: str, needles: tuple[str, ...]) -> str | None:
    lowered_needles = tuple(needle.lower() for needle in needles)
    for line in output.splitlines():
        lowered = line.lower()
        if any(needle in lowered for needle in lowered_needles):
            return line.strip()
    return None


def _matching_lines(output: str, needles: tuple[str, ...]) -> list[str]:
    lowered_needles = tuple(needle.lower() for needle in needles)
    return [
        line.strip()
        for line in output.splitlines()
        if any(needle in line.lower() for needle in lowered_needles)
    ]


def _parse_pci_identity(line: str) -> tuple[str | None, str | None, str | None]:
    pci_address = line.split(maxsplit=1)[0] if line.strip() else None
    ids = re.findall(r"\[([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\]", line)
    if ids:
        vendor_id, product_id = ids[-1]
        return pci_address, vendor_id.lower(), product_id.lower()
    return pci_address, None, None


def _camera_usb_ids(name: str, lsusb_output: str) -> tuple[str | None, str | None]:
    for line in lsusb_output.splitlines():
        lowered = line.lower()
        if "046d:085e" in lowered or any(part and part in lowered for part in name.lower().split()):
            match = re.search(r"ID\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})", line)
            if match:
                return match.group(1).lower(), match.group(2).lower()
    return None, None


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique_values.append(value)
    return unique_values


def _is_video_device_path(path: str) -> bool:
    return bool(re.fullmatch(r"/dev/video\d+", path))

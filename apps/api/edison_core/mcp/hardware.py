from __future__ import annotations

from edison_core.config import load_settings
from edison_core.mcp.runtime import MCPServer, MCPTool, object_schema
from edison_core.services.hardware_devices import HardwareDeviceService
from edison_core.services.model_registry import ModelRegistry
from edison_core.services.system_status import GPUFanControlService, SystemStatusService


def create_server(
    hardware: HardwareDeviceService | None = None,
    status_service: SystemStatusService | None = None,
    fan_control_service: GPUFanControlService | None = None,
) -> MCPServer:
    settings = load_settings()
    model_registry = ModelRegistry.from_file(settings.model_registry_path)
    status = status_service or SystemStatusService(settings, model_registry)
    fans = fan_control_service or GPUFanControlService(settings, status.gpu_manager)
    devices = hardware or HardwareDeviceService(settings)
    return MCPServer(
        name="edison-hardware",
        version="0.1.0",
        tools=[
            MCPTool(
                name="hardware.status",
                description="Return Edison GPU, storage, Hailo, and camera hardware status.",
                input_schema=object_schema(),
                handler=lambda _: {
                    "system": status.snapshot(),
                    "devices": devices.snapshot(),
                },
            ),
            MCPTool(
                name="hardware.fans",
                description="Return GPU fan controller telemetry and current policies.",
                input_schema=object_schema(),
                handler=lambda _: fans.snapshot(),
            ),
            MCPTool(
                name="hailo.status",
                description="Return Hailo-8 accelerator readiness.",
                input_schema=object_schema(),
                handler=lambda _: next(
                    (item for item in devices.detect_accelerators() if item.kind == "hailo8"),
                    None,
                ),
            ),
            MCPTool(
                name="camera.status",
                description="Return detected camera devices and capture readiness.",
                input_schema=object_schema(),
                handler=lambda _: devices.detect_cameras(),
            ),
        ],
    )


def main() -> None:
    create_server().serve_stdio()


if __name__ == "__main__":
    main()

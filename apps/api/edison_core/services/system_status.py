from __future__ import annotations

import os
import re
import subprocess

from edison_core.config import EdisonSettings
from edison_core.schemas import (
    GPUDevice,
    GPUFanControlSnapshot,
    GPUFanControlState,
    GPUFanControlUpdate,
    GPUFanCurvePoint,
    GPUFanPolicy,
    ModelStatus,
    SystemStatus,
)
from edison_core.services.model_registry import ModelRegistry


class GPUResourceManager:
    def detect_gpus(self) -> list[GPUDevice]:
        command = [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.used,temperature.gpu,utilization.gpu,power.draw,fan.speed",
            "--format=csv,noheader,nounits",
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=2, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []
        if result.returncode != 0:
            return []
        return [_parse_gpu_line(line) for line in result.stdout.splitlines() if line.strip()]


class SystemStatusService:
    def __init__(self, settings: EdisonSettings, registry: ModelRegistry) -> None:
        self.settings = settings
        self.registry = registry
        self.gpu_manager = GPUResourceManager()

    def snapshot(self) -> SystemStatus:
        profiles = self.registry.list_profiles()
        configured_models = [profile for profile in profiles if profile.status != ModelStatus.NOT_CONFIGURED]
        return SystemStatus(
            service="edison-core-api",
            version="0.1.0",
            environment=self.settings.environment,
            database_path=str(self.settings.database_path),
            model_count=len(profiles),
            configured_model_count=len(configured_models),
            gpu_devices=self.gpu_manager.detect_gpus(),
            storage_roots={
                "artifacts": str(self.settings.artifact_root),
                "logs": str(self.settings.log_root),
                "projects": str(self.settings.project_root),
            },
        )


class GPUFanControlService:
    def __init__(self, settings: EdisonSettings, gpu_manager: GPUResourceManager | None = None) -> None:
        self.settings = settings
        self.gpu_manager = gpu_manager or GPUResourceManager()
        self._policies: dict[int, GPUFanPolicy] = {}

    def snapshot(self) -> GPUFanControlSnapshot:
        return GPUFanControlSnapshot(
            hardware_control_enabled=self.settings.gpu_fan_control_enabled,
            backend=self.settings.gpu_fan_control_backend,
            controllers=[self._state_for_gpu(gpu, apply=False) for gpu in self.gpu_manager.detect_gpus()],
        )

    def update_policy(self, gpu_index: int, payload: GPUFanControlUpdate) -> GPUFanControlState:
        policy = GPUFanPolicy(
            mode=payload.mode,
            manual_speed_percent=payload.manual_speed_percent,
            curve=payload.curve or _default_curve(),
        )
        self._policies[gpu_index] = policy
        gpu = self._find_gpu(gpu_index)
        return self._state_for_gpu(gpu, apply=True)

    def _state_for_gpu(self, gpu: GPUDevice, apply: bool) -> GPUFanControlState:
        policy = self._policies.setdefault(gpu.index, GPUFanPolicy(curve=_default_curve()))
        target_speed = _target_speed(policy, gpu.temperature_c, gpu.fan_speed_percent)
        target_fan_ids = (
            self._fan_ids_for_gpu(gpu.index, self._nvidia_env())
            if self.settings.gpu_fan_control_backend == "nvidia-settings"
            else []
        )
        applied, detail = self._apply_policy(gpu.index, policy, target_speed) if apply else (
            False,
            "Fan controller is ready.",
        )
        return GPUFanControlState(
            gpu=gpu,
            policy=policy,
            target_speed_percent=target_speed,
            target_fan_ids=target_fan_ids,
            hardware_control_enabled=self.settings.gpu_fan_control_enabled,
            backend=self.settings.gpu_fan_control_backend,
            applied=applied,
            detail=detail,
        )

    def _find_gpu(self, gpu_index: int) -> GPUDevice:
        for gpu in self.gpu_manager.detect_gpus():
            if gpu.index == gpu_index:
                return gpu
        return GPUDevice(index=gpu_index, name=f"GPU {gpu_index}")

    def _apply_policy(self, gpu_index: int, policy: GPUFanPolicy, target_speed: int | None) -> tuple[bool, str]:
        if not self.settings.gpu_fan_control_enabled:
            return False, "Hardware fan writes are disabled; policy is saved for this API process."
        if self.settings.gpu_fan_control_backend != "nvidia-settings":
            return False, f"Backend {self.settings.gpu_fan_control_backend!r} does not support fan writes."
        env = self._nvidia_env()
        fan_ids = self._fan_ids_for_gpu(gpu_index, env)
        if not fan_ids and policy.mode != "auto":
            return False, "No writable NVIDIA fan targets were detected."
        commands = [["nvidia-settings", "-a", f"[gpu:{gpu_index}]/GPUFanControlState=0"]]
        if policy.mode != "auto" and target_speed is not None:
            command = ["nvidia-settings", "-a", f"[gpu:{gpu_index}]/GPUFanControlState=1"]
            for fan_id in fan_ids:
                command.extend(["-a", f"[fan:{fan_id}]/GPUTargetFanSpeed={target_speed}"])
            commands = [command]
        for command in commands:
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=3, check=False, env=env)
            except (FileNotFoundError, subprocess.TimeoutExpired) as error:
                return False, f"Fan write failed: {error}"
            if result.returncode != 0:
                detail = result.stderr.strip() or result.stdout.strip() or "nvidia-settings returned an error"
                return False, detail
        targets = ", ".join(f"fan:{fan_id}" for fan_id in fan_ids) if fan_ids else f"gpu:{gpu_index}"
        return True, f"Fan policy applied through nvidia-settings on {targets}."

    def _fan_ids_for_gpu(self, gpu_index: int, env: dict[str, str]) -> list[int]:
        configured = self.settings.gpu_fan_target_map.get(gpu_index)
        if configured:
            return configured
        detected = self._detect_fan_ids(env)
        if not detected:
            return [gpu_index]
        gpu_count = len(self.gpu_manager.detect_gpus())
        if gpu_count == 3 and len(detected) == 5:
            default_map = {0: detected[:1], 1: detected[1:3], 2: detected[3:5]}
            return default_map.get(gpu_index, [])
        return [gpu_index] if gpu_index in detected else detected

    def _detect_fan_ids(self, env: dict[str, str]) -> list[int]:
        try:
            result = subprocess.run(
                ["nvidia-settings", "-q", "fans"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
                env=env,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []
        if result.returncode != 0:
            return []
        fan_ids = {int(match.group(1)) for match in re.finditer(r"\[fan:(\d+)\]", result.stdout)}
        return sorted(fan_ids)

    def _nvidia_env(self) -> dict[str, str]:
        return {**os.environ, "DISPLAY": self.settings.gpu_fan_control_display}


def _parse_gpu_line(line: str) -> GPUDevice:
    parts = [part.strip() for part in line.split(",")]
    return GPUDevice(
        index=_int_or_none(parts[0]) or 0,
        name=parts[1] if len(parts) > 1 else "Unknown GPU",
        vram_total_mb=_int_or_none(_part(parts, 2)),
        vram_used_mb=_int_or_none(_part(parts, 3)),
        temperature_c=_int_or_none(_part(parts, 4)),
        utilization_percent=_int_or_none(_part(parts, 5)),
        power_draw_watts=_float_or_none(_part(parts, 6)),
        fan_speed_percent=_int_or_none(_part(parts, 7)),
    )


def _default_curve() -> list[GPUFanCurvePoint]:
    return [
        GPUFanCurvePoint(temperature_c=35, speed_percent=30),
        GPUFanCurvePoint(temperature_c=55, speed_percent=50),
        GPUFanCurvePoint(temperature_c=70, speed_percent=72),
        GPUFanCurvePoint(temperature_c=82, speed_percent=90),
    ]


def _target_speed(policy: GPUFanPolicy, temperature_c: int | None, current_speed: int | None) -> int | None:
    if policy.mode == "auto":
        return current_speed
    if policy.mode == "manual":
        return policy.manual_speed_percent
    curve = sorted(policy.curve or _default_curve(), key=lambda point: point.temperature_c)
    if temperature_c is None:
        return curve[0].speed_percent if curve else current_speed
    target = curve[0].speed_percent
    for point in curve:
        if temperature_c >= point.temperature_c:
            target = point.speed_percent
    return target


def _part(parts: list[str], index: int) -> str | None:
    return parts[index] if len(parts) > index else None


def _int_or_none(value: str | None) -> int | None:
    if not value or value in {"N/A", "[Not Supported]"}:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _float_or_none(value: str | None) -> float | None:
    if not value or value in {"N/A", "[Not Supported]"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None

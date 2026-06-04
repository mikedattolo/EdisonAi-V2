from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class EdisonSettings(BaseModel):
    app_name: str = "EDISON V2"
    environment: str = "local"
    debug: bool = True
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    database_path: Path = PROJECT_ROOT / "data" / "edison.sqlite3"
    artifact_root: Path = PROJECT_ROOT / "artifacts"
    log_root: Path = PROJECT_ROOT / "logs"
    project_root: Path = PROJECT_ROOT / "projects"
    model_registry_path: Path = PROJECT_ROOT / "config" / "model-registry.example.json"
    default_chat_model: str = "local-general-chat"
    default_coding_model: str = "local-coding"
    default_reasoning_model: str = "local-reasoning"
    comfyui_base_url: str = "http://127.0.0.1:8188"
    comfyui_timeout_seconds: float = 2.0
    invokeai_base_url: str | None = None
    invokeai_timeout_seconds: float = 2.0
    wan22_base_url: str | None = None
    wan22_timeout_seconds: float = 2.0
    modly_base_url: str | None = None
    modly_timeout_seconds: float = 2.0
    workflow_root: Path = PROJECT_ROOT / "workflows"
    integration_discovery_path: Path = PROJECT_ROOT / "config" / "integration-discovery.local.json"
    gpu_fan_control_enabled: bool = False
    gpu_fan_control_backend: str = "monitor"
    gpu_fan_control_display: str = ":99"
    gpu_fan_target_map: dict[int, list[int]] = Field(default_factory=dict)
    workspace_roots: list[Path] = Field(default_factory=lambda: [PROJECT_ROOT])
    require_approval_for_destructive_tools: bool = True
    require_approval_for_external_side_effects: bool = True


def load_settings(config_path: str | Path | None = None) -> EdisonSettings:
    path = Path(
        config_path
        or os.getenv("EDISON_CONFIG_PATH")
        or PROJECT_ROOT / "config" / "edison.example.toml"
    )
    raw = _read_toml(path) if path.exists() else {}

    app = raw.get("app", {})
    storage = raw.get("storage", {})
    models = raw.get("models", {})
    media = raw.get("media", {})
    hardware = raw.get("hardware", {})
    security = raw.get("security", {})

    settings = EdisonSettings(
        app_name=os.getenv("EDISON_APP_NAME", app.get("name", "EDISON V2")),
        environment=os.getenv("EDISON_ENVIRONMENT", app.get("environment", "local")),
        debug=_bool_env("EDISON_DEBUG", app.get("debug", True)),
        api_host=os.getenv("EDISON_API_HOST", app.get("api_host", "127.0.0.1")),
        api_port=int(os.getenv("EDISON_API_PORT", app.get("api_port", 8000))),
        cors_origins=_list_env("EDISON_CORS_ORIGINS", app.get("cors_origins")),
        database_path=_resolve_path(
            os.getenv("EDISON_DATABASE_PATH", storage.get("database_path", "data/edison.sqlite3"))
        ),
        artifact_root=_resolve_path(
            os.getenv("EDISON_ARTIFACT_ROOT", storage.get("artifact_root", "artifacts"))
        ),
        log_root=_resolve_path(os.getenv("EDISON_LOG_ROOT", storage.get("log_root", "logs"))),
        project_root=_resolve_path(os.getenv("EDISON_PROJECT_ROOT", storage.get("project_root", "projects"))),
        model_registry_path=_resolve_path(
            os.getenv(
                "EDISON_MODEL_REGISTRY_PATH",
                models.get("registry_path", "config/model-registry.example.json"),
            )
        ),
        default_chat_model=os.getenv(
            "EDISON_DEFAULT_CHAT_MODEL", models.get("default_chat_model", "local-general-chat")
        ),
        default_coding_model=os.getenv(
            "EDISON_DEFAULT_CODING_MODEL", models.get("default_coding_model", "local-coding")
        ),
        default_reasoning_model=os.getenv(
            "EDISON_DEFAULT_REASONING_MODEL",
            models.get("default_reasoning_model", "local-reasoning"),
        ),
        comfyui_base_url=os.getenv(
            "EDISON_COMFYUI_BASE_URL", media.get("comfyui_base_url", "http://127.0.0.1:8188")
        ),
        comfyui_timeout_seconds=float(
            os.getenv("EDISON_COMFYUI_TIMEOUT_SECONDS", media.get("comfyui_timeout_seconds", 2.0))
        ),
        invokeai_base_url=os.getenv("EDISON_INVOKEAI_BASE_URL", media.get("invokeai_base_url")),
        invokeai_timeout_seconds=float(
            os.getenv("EDISON_INVOKEAI_TIMEOUT_SECONDS", media.get("invokeai_timeout_seconds", 2.0))
        ),
        wan22_base_url=os.getenv("EDISON_WAN22_BASE_URL", media.get("wan22_base_url")),
        wan22_timeout_seconds=float(
            os.getenv("EDISON_WAN22_TIMEOUT_SECONDS", media.get("wan22_timeout_seconds", 2.0))
        ),
        modly_base_url=os.getenv("EDISON_MODLY_BASE_URL", media.get("modly_base_url")),
        modly_timeout_seconds=float(
            os.getenv("EDISON_MODLY_TIMEOUT_SECONDS", media.get("modly_timeout_seconds", 2.0))
        ),
        workflow_root=_resolve_path(
            os.getenv("EDISON_WORKFLOW_ROOT", media.get("workflow_root", "workflows"))
        ),
        integration_discovery_path=_resolve_path(
            os.getenv(
                "EDISON_INTEGRATION_DISCOVERY_PATH",
                raw.get("integrations", {}).get("discovery_path", "config/integration-discovery.local.json"),
            )
        ),
        gpu_fan_control_enabled=_bool_env(
            "EDISON_GPU_FAN_CONTROL_ENABLED", hardware.get("gpu_fan_control_enabled", False)
        ),
        gpu_fan_control_backend=os.getenv(
            "EDISON_GPU_FAN_CONTROL_BACKEND", hardware.get("gpu_fan_control_backend", "monitor")
        ),
        gpu_fan_control_display=os.getenv(
            "EDISON_GPU_FAN_CONTROL_DISPLAY", hardware.get("gpu_fan_control_display", ":99")
        ),
        gpu_fan_target_map=_fan_target_map_env(
            "EDISON_GPU_FAN_TARGET_MAP", hardware.get("gpu_fan_target_map", {})
        ),
        workspace_roots=[
            _resolve_path(root)
            for root in _list_env("EDISON_WORKSPACE_ROOTS", security.get("workspace_roots", ["."]))
        ],
        require_approval_for_destructive_tools=bool(
            security.get("require_approval_for_destructive_tools", True)
        ),
        require_approval_for_external_side_effects=bool(
            security.get("require_approval_for_external_side_effects", True)
        ),
    )
    return settings


def _read_toml(path: Path) -> dict:
    with path.open("rb") as config_file:
        return tomllib.load(config_file)


def _resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _list_env(name: str, default: list[str] | None) -> list[str]:
    value = os.getenv(name)
    if value:
        return [item.strip() for item in value.split(",") if item.strip()]
    return default or ["http://localhost:5173", "http://127.0.0.1:5173"]


def _fan_target_map_env(name: str, default: object) -> dict[int, list[int]]:
    value = os.getenv(name)
    raw = value if value else default
    if isinstance(raw, dict):
        return {
            int(gpu_index): [int(fan_id) for fan_id in _coerce_list(fan_ids)]
            for gpu_index, fan_ids in raw.items()
        }
    if isinstance(raw, list):
        pairs = raw
    elif isinstance(raw, str):
        pairs = [item.strip() for item in raw.split(";") if item.strip()]
    else:
        return {}
    parsed: dict[int, list[int]] = {}
    for pair in pairs:
        if not isinstance(pair, str) or ":" not in pair:
            continue
        gpu_index, fan_ids = pair.split(":", 1)
        parsed[int(gpu_index.strip())] = [
            int(fan_id.strip()) for fan_id in fan_ids.split(",") if fan_id.strip()
        ]
    return parsed


def _coerce_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [value]

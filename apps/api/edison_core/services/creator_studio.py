from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from edison_core.config import EdisonSettings
from edison_core.schemas import CreatorStudioAssetRecord, CreatorStudioDatasetRecord, CreatorStudioStatus


CREATOR_GUARDRAILS = [
    "AI-generated or rights-cleared fictional adult personas only",
    "No nude, pornographic, or sexually explicit output",
    "No real-person likeness, celebrity impersonation, or non-consensual datasets",
    "No minors or youth-coded creator content",
]

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
SAFE_DATASET_NAMES = {"sfw", "training_ready", "datasets"}
UNSAFE_PATH_PARTS = {"nsfw", "adult", "restricted", "porn", "explicit"}
MODEL_SUFFIXES = {".safetensors", ".ckpt", ".gguf", ".bin", ".pt", ".pth"}
WORKFLOW_SUFFIXES = {".json"}
SCRIPT_SUFFIXES = {".py", ".bat", ".ps1", ".sh"}
CONFIG_SUFFIXES = {".yaml", ".yml", ".toml"}
DOCUMENT_SUFFIXES = {".md", ".txt"}


class CreatorStudioService:
    def __init__(self, settings: EdisonSettings) -> None:
        self.settings = settings

    def status(self) -> CreatorStudioStatus:
        configured_path = self.settings.creator_studio_source_path
        if configured_path is None:
            return CreatorStudioStatus(
                status="setup_required",
                detail="Creator Studio asset path is not configured.",
                guardrails=CREATOR_GUARDRAILS,
                metadata={"planning_model": "qwen3.6-35b-a3b-hauhaucs-coding"},
            )

        root = _normalize_creator_root(configured_path)
        if root is None:
            return CreatorStudioStatus(
                status="setup_required",
                source_path=str(configured_path),
                detail="Creator Studio assets were not found. Sync the safe PixelAI creator bundle to Edison first.",
                guardrails=CREATOR_GUARDRAILS,
                metadata={
                    "expected_layout": "creator_studio/templates, creator_studio/config, creator_studio/data",
                    "planning_model": "qwen3.6-35b-a3b-hauhaucs-coding",
                },
            )

        datasets = _discover_datasets(root)
        workflow_templates = _discover_workflow_templates(root)
        restricted_assets = _discover_restricted_assets(root)
        detail = "Creator Studio assets are available for safe virtual creator workflows."
        if not workflow_templates:
            detail = "Creator Studio root is present, but no workflow templates were found yet."
        return CreatorStudioStatus(
            status="ready",
            source_path=str(configured_path),
            normalized_root=str(root),
            detail=detail,
            datasets=datasets,
            workflow_templates=workflow_templates,
            restricted_assets=restricted_assets,
            guardrails=CREATOR_GUARDRAILS,
            metadata={
                "dataset_count": len(datasets),
                "workflow_template_count": len(workflow_templates),
                "restricted_asset_count": len(restricted_assets),
                "restricted_model_candidate_count": len([item for item in restricted_assets if item.kind == "model"]),
                "supports_photo": True,
                "supports_video": True,
                "supports_dataset_plans": True,
                "planning_model": "qwen3.6-35b-a3b-hauhaucs-coding",
            },
        )


def _normalize_creator_root(path: Path) -> Path | None:
    candidates = [
        path,
        path / "creator_studio",
        path / "pixelaiLabs_ComfyUI_Installer" / "creator_studio",
    ]
    for candidate in candidates:
        if not candidate.exists() or not candidate.is_dir():
            continue
        if (candidate / "templates").exists() or (candidate / "config").exists() or (candidate / "data").exists():
            return candidate
    return None


def _discover_workflow_templates(root: Path) -> list[str]:
    template_roots = [
        root / "templates" / "workflows",
        root / "comfyui" / "workflows",
        root / "restricted_assets" / "workflows",
        root / "restricted_assets" / "ComfyUI" / "user" / "default" / "workflows",
    ]
    templates: list[str] = []
    for template_root in template_roots:
        if not template_root.exists():
            continue
        for path in sorted(template_root.glob("*.json")):
            templates.append(path.name)
    return templates[:24]


def _discover_datasets(root: Path) -> list[CreatorStudioDatasetRecord]:
    dataset_roots = [
        root / "data" / "datasets",
        root / "data" / "lena_hub" / "sfw",
        root / "data" / "lena_hub" / "training_ready",
        root / "data" / "lora_training" / "lena_sfw",
        root / "datasets",
    ]
    records: list[CreatorStudioDatasetRecord] = []
    seen: set[Path] = set()
    for dataset_root in dataset_roots:
        if not dataset_root.exists() or _has_unsafe_path_part(dataset_root):
            continue
        candidate_dirs = [dataset_root]
        if dataset_root.name in SAFE_DATASET_NAMES:
            candidate_dirs.extend([child for child in dataset_root.iterdir() if child.is_dir()])
        for candidate in candidate_dirs:
            resolved = candidate.resolve()
            if resolved in seen or _has_unsafe_path_part(candidate):
                continue
            seen.add(resolved)
            item_counts = _count_media(candidate)
            total = item_counts["image"] + item_counts["video"]
            if total == 0 and candidate != dataset_root:
                continue
            kind = _dataset_kind(item_counts)
            records.append(
                CreatorStudioDatasetRecord(
                    id=_dataset_id(candidate),
                    name=_friendly_dataset_name(candidate),
                    root_path=str(candidate),
                    kind=kind,
                    status="ready" if total else "empty",
                    item_count=total,
                    trigger_token=_trigger_token(candidate),
                    metadata={
                        "image_count": item_counts["image"],
                        "video_count": item_counts["video"],
                        "source": "pixelai-creator-studio",
                    },
                )
            )
    return sorted(records, key=lambda item: (item.status != "ready", item.name.lower()))[:24]


def _count_media(root: Path) -> dict[str, int]:
    counts = {"image": 0, "video": 0}
    try:
        paths = root.rglob("*")
        for path in paths:
            if not path.is_file() or _has_unsafe_path_part(path):
                continue
            suffix = path.suffix.lower()
            if suffix in IMAGE_SUFFIXES:
                counts["image"] += 1
            elif suffix in VIDEO_SUFFIXES:
                counts["video"] += 1
    except OSError:
        return counts
    return counts


def _dataset_kind(counts: dict[str, int]) -> Literal["image", "video", "mixed", "unknown"]:
    if counts["image"] and counts["video"]:
        return "mixed"
    if counts["image"]:
        return "image"
    if counts["video"]:
        return "video"
    return "unknown"


def _discover_restricted_assets(root: Path) -> list[CreatorStudioAssetRecord]:
    assets: list[CreatorStudioAssetRecord] = []
    seen: set[str] = set()
    restricted_root = root / "restricted_assets"
    if restricted_root.exists():
        for path in sorted(restricted_root.rglob("*")):
            if not path.is_file() or _is_media_file(path):
                continue
            record = _asset_record_from_path(
                path,
                source_path=None,
                copied_root=root,
                status="available",
                tags=["restricted-labeled", "copied"],
            )
            assets.append(record)
            seen.add(record.id)

    for record in _restricted_manifest_assets(root):
        if record.id in seen:
            continue
        assets.append(record)
        seen.add(record.id)
    return sorted(assets, key=lambda item: (item.kind, item.name.lower()))[:80]


def _restricted_manifest_assets(root: Path) -> list[CreatorStudioAssetRecord]:
    manifest_path = root / "edison_creator_bundle_manifest.json"
    if not manifest_path.exists():
        return []
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    items = raw.get("restricted_asset_candidates")
    if not isinstance(items, list):
        return []
    records: list[CreatorStudioAssetRecord] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        source_path = str(item.get("source_path") or "")
        name = str(item.get("name") or Path(source_path).name or "Restricted asset")
        suffix = Path(name).suffix.lower()
        kind = _asset_kind_from_suffix(suffix)
        status = "candidate" if kind == "model" else "cataloged"
        record = CreatorStudioAssetRecord(
            id=_asset_id(source_path or name),
            name=name,
            kind=kind,
            status=status,
            source_path=source_path or None,
            copied_path=None,
            size_bytes=_int_or_none(item.get("size_bytes")),
            tags=["restricted-labeled", "manifest"],
            metadata={
                "original_relative_path": item.get("relative_path"),
                "copied": bool(item.get("copied")),
            },
        )
        records.append(record)
    return records


def _asset_record_from_path(
    path: Path,
    *,
    source_path: str | None,
    copied_root: Path,
    status: Literal["available", "candidate", "cataloged"],
    tags: list[str],
) -> CreatorStudioAssetRecord:
    suffix = path.suffix.lower()
    copied_path = path.relative_to(copied_root).as_posix() if path.is_relative_to(copied_root) else str(path)
    return CreatorStudioAssetRecord(
        id=_asset_id(str(path)),
        name=path.name,
        kind=_asset_kind_from_suffix(suffix),
        status=status,
        source_path=source_path,
        copied_path=copied_path,
        size_bytes=path.stat().st_size if path.exists() else None,
        tags=tags,
        metadata={"suffix": suffix},
    )


def _asset_kind_from_suffix(suffix: str) -> Literal["workflow", "model", "script", "config", "document", "other"]:
    if suffix in WORKFLOW_SUFFIXES:
        return "workflow"
    if suffix in MODEL_SUFFIXES:
        return "model"
    if suffix in SCRIPT_SUFFIXES:
        return "script"
    if suffix in CONFIG_SUFFIXES:
        return "config"
    if suffix in DOCUMENT_SUFFIXES:
        return "document"
    return "other"


def _asset_id(value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    return f"creator_asset_{digest}"


def _is_media_file(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_SUFFIXES | VIDEO_SUFFIXES


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _dataset_id(path: Path) -> str:
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]
    return f"creator_ds_{digest}"


def _friendly_dataset_name(path: Path) -> str:
    name = path.name.replace("_", " ").replace("-", " ").strip()
    return " ".join(part.capitalize() for part in name.split()) or "Creator Dataset"


def _trigger_token(path: Path) -> str:
    token = "".join(character.lower() if character.isalnum() else "_" for character in path.name)
    token = "_".join(part for part in token.split("_") if part)
    return f"{token}_ai" if token else "creator_ai"


def _has_unsafe_path_part(path: Path) -> bool:
    lowered_parts = [part.lower() for part in path.parts]
    return any(any(marker in part for marker in UNSAFE_PATH_PARTS) for part in lowered_parts)

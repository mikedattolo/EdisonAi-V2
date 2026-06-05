from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from edison_core.config import EdisonSettings
from edison_core.schemas import CreatorStudioDatasetRecord, CreatorStudioStatus


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
            )

        root = _normalize_creator_root(configured_path)
        if root is None:
            return CreatorStudioStatus(
                status="setup_required",
                source_path=str(configured_path),
                detail="Creator Studio assets were not found. Sync the safe PixelAI creator bundle to Edison first.",
                guardrails=CREATOR_GUARDRAILS,
                metadata={"expected_layout": "creator_studio/templates, creator_studio/config, creator_studio/data"},
            )

        datasets = _discover_datasets(root)
        workflow_templates = _discover_workflow_templates(root)
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
            guardrails=CREATOR_GUARDRAILS,
            metadata={
                "dataset_count": len(datasets),
                "workflow_template_count": len(workflow_templates),
                "supports_photo": True,
                "supports_video": True,
                "supports_dataset_plans": True,
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
    template_roots = [root / "templates" / "workflows", root / "comfyui" / "workflows"]
    templates: list[str] = []
    for template_root in template_roots:
        if not template_root.exists():
            continue
        for path in sorted(template_root.glob("*.json")):
            if _has_unsafe_path_part(path):
                continue
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

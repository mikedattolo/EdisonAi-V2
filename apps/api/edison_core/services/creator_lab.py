"""Creator Lab: managed datasets, LoRA/workflow toggles, ComfyUI workflow graphs,
VLM critique, and the staging ground for multi-GPU LoRA training.

This is a self-contained, on-disk managed studio so it works even when the
optional PixelAI bundle is not synced. All content stays inside the same
non-negotiable safety guardrails as the rest of Creator Studio."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import httpx

from edison_core.schemas import (
    CreatorLabDataset,
    CreatorLabDatasetCreateRequest,
    CreatorLabGpu,
    CreatorLabImage,
    CreatorLabLoraType,
    CreatorLabOverview,
    CreatorLabSelectionRequest,
    CreatorLabWorkflow,
    CreatorVlmCritique,
    CreatorWorkflowGraph,
    CreatorWorkflowNode,
)
from edison_core.services.creator_studio import (
    CREATOR_GUARDRAILS,
    creator_guard_reason,
)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_IMAGE_BYTES = 25 * 1024 * 1024
OLLAMA_BASE_URL = os.getenv("EDISON_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
VISION_MODELS = ["local-vision", "qwen2.5vl:7b"]
DEFAULT_SDXL_BASE = "sd_xl_base_1.0.safetensors"


class CreatorLabError(Exception):
    """Raised for guardrail or validation failures the API surfaces as 4xx."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class CreatorLabService:
    def __init__(self, root: Path, comfyui_models_path: Path | None = None) -> None:
        self.root = Path(root)
        self.datasets_dir = self.root / "datasets"
        self.outputs_dir = self.root / "outputs"
        self.lab_file = self.root / "lab.json"
        self.comfyui_models_path = comfyui_models_path

    def initialize(self) -> None:
        self.datasets_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

    # -- overview -----------------------------------------------------------

    def overview(self) -> CreatorLabOverview:
        self.initialize()
        selection = self._read_lab()
        datasets = self.list_datasets()
        active_dataset = selection.get("active_dataset_id")
        if active_dataset and not any(item.id == active_dataset for item in datasets):
            active_dataset = None
        return CreatorLabOverview(
            root_path=str(self.root),
            datasets=datasets,
            lora_types=self.lora_types(),
            workflows=self.workflows(),
            gpus=self.gpus(),
            active_dataset_id=active_dataset or (datasets[0].id if datasets else None),
            active_lora_type=selection.get("active_lora_type", "sdxl"),
            active_workflow=selection.get("active_workflow", "sdxl_txt2img_lora"),
            training_available=self.training_available(),
            guardrails=CREATOR_GUARDRAILS,
            metadata={
                "dataset_count": len(datasets),
                "vision_model": VISION_MODELS[0],
                "auto_critique": True,
            },
        )

    # -- datasets -----------------------------------------------------------

    def list_datasets(self) -> list[CreatorLabDataset]:
        self.initialize()
        records: list[CreatorLabDataset] = []
        for child in sorted(self.datasets_dir.iterdir() if self.datasets_dir.exists() else []):
            if not child.is_dir():
                continue
            record = self._load_dataset(child, include_images=False)
            if record is not None:
                records.append(record)
        records.sort(key=lambda item: (item.created_at or ""), reverse=True)
        return records

    def get_dataset(self, dataset_id: str) -> CreatorLabDataset:
        path = self._dataset_path(dataset_id)
        record = self._load_dataset(path, include_images=True)
        if record is None:
            raise CreatorLabError("Dataset not found.", status_code=404)
        return record

    def create_dataset(self, request: CreatorLabDatasetCreateRequest) -> CreatorLabDataset:
        name = request.name.strip()
        if not name:
            raise CreatorLabError("Dataset name is required.")
        reason = creator_guard_reason(f"{name} {request.notes or ''} {request.trigger_token or ''}")
        if reason:
            raise CreatorLabError(reason)
        dataset_id = self._make_dataset_id(name)
        path = self.datasets_dir / dataset_id
        if path.exists():
            raise CreatorLabError("A dataset with this name already exists.", status_code=409)
        (path / "images").mkdir(parents=True, exist_ok=True)
        trigger = _slug_token(request.trigger_token or name)
        config = {
            "id": dataset_id,
            "name": name,
            "trigger_token": trigger,
            "lora_type": request.lora_type or "sdxl",
            "base_model": DEFAULT_SDXL_BASE if (request.lora_type or "sdxl") == "sdxl" else None,
            "workflow": request.workflow or "sdxl_txt2img_lora",
            "notes": (request.notes or "").strip() or None,
            "created_at": _now_iso(),
        }
        self._write_dataset_config(path, config)
        return self._load_dataset(path, include_images=True)  # type: ignore[return-value]

    def add_images(self, dataset_id: str, files: list[tuple[str, bytes]]) -> CreatorLabDataset:
        path = self._dataset_path(dataset_id)
        if not path.exists():
            raise CreatorLabError("Dataset not found.", status_code=404)
        images_dir = path / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        saved = 0
        for filename, data in files:
            suffix = Path(filename).suffix.lower()
            if suffix not in IMAGE_SUFFIXES:
                continue
            if len(data) > MAX_IMAGE_BYTES or not data:
                continue
            reason = creator_guard_reason(filename)
            if reason:
                raise CreatorLabError(reason)
            target = self._unique_image_path(images_dir, filename)
            target.write_bytes(data)
            saved += 1
        if saved == 0:
            raise CreatorLabError("No valid images were uploaded (use jpg/png/webp under 25MB).")
        return self.get_dataset(dataset_id)

    def delete_image(self, dataset_id: str, image_id: str) -> CreatorLabDataset:
        images_dir = self._dataset_path(dataset_id) / "images"
        target = self._safe_child(images_dir, image_id)
        if target.exists():
            target.unlink()
        return self.get_dataset(dataset_id)

    def delete_dataset(self, dataset_id: str) -> None:
        path = self._dataset_path(dataset_id)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        selection = self._read_lab()
        if selection.get("active_dataset_id") == dataset_id:
            selection["active_dataset_id"] = None
            self._write_lab(selection)

    def image_file(self, dataset_id: str, image_id: str) -> Path:
        images_dir = self._dataset_path(dataset_id) / "images"
        target = self._safe_child(images_dir, image_id)
        if not target.exists() or not target.is_file():
            raise CreatorLabError("Image not found.", status_code=404)
        return target

    # -- selections ---------------------------------------------------------

    def set_selection(self, request: CreatorLabSelectionRequest) -> CreatorLabOverview:
        selection = self._read_lab()
        if request.active_dataset_id is not None:
            selection["active_dataset_id"] = request.active_dataset_id or None
        if request.active_lora_type is not None:
            selection["active_lora_type"] = request.active_lora_type
        if request.active_workflow is not None:
            selection["active_workflow"] = request.active_workflow
        self._write_lab(selection)
        return self.overview()

    # -- lora types & workflows --------------------------------------------

    def lora_types(self) -> list[CreatorLabLoraType]:
        sdxl_available = self._checkpoint_exists(DEFAULT_SDXL_BASE)
        return [
            CreatorLabLoraType(
                id="sdxl",
                label="SDXL 1.0",
                base=DEFAULT_SDXL_BASE,
                available=sdxl_available,
                detail="Photoreal 1024px. Base checkpoint detected." if sdxl_available else "SDXL base checkpoint missing.",
            ),
            CreatorLabLoraType(
                id="sd15",
                label="SD 1.5",
                base="v1-5-pruned-emaonly.safetensors",
                available=self._checkpoint_exists("v1-5-pruned-emaonly.safetensors"),
                detail="Lightweight 512px training.",
            ),
            CreatorLabLoraType(
                id="flux",
                label="Flux.1 dev",
                base="flux1-dev.safetensors",
                available=self._checkpoint_exists("flux1-dev.safetensors"),
                detail="High fidelity. Requires Flux weights download.",
            ),
            CreatorLabLoraType(
                id="pony",
                label="Pony / Illustrious",
                base="ponyDiffusionV6XL.safetensors",
                available=self._checkpoint_exists("ponyDiffusionV6XL.safetensors"),
                detail="Stylized SDXL derivative.",
            ),
        ]

    def workflows(self) -> list[CreatorLabWorkflow]:
        out: list[CreatorLabWorkflow] = []
        for template in _BUILTIN_WORKFLOWS.values():
            graph = template["graph"]
            out.append(
                CreatorLabWorkflow(
                    id=template["id"],
                    label=template["label"],
                    kind=template.get("kind", "image"),
                    builtin=True,
                    node_count=len(graph),
                    detail=template.get("detail"),
                )
            )
        return out

    def workflow_graph(self, workflow_id: str) -> CreatorWorkflowGraph:
        template = _BUILTIN_WORKFLOWS.get(workflow_id)
        if template is None:
            raise CreatorLabError("Workflow not found.", status_code=404)
        graph = template["graph"]
        nodes = [
            CreatorWorkflowNode(
                id=node_id,
                type=str(node.get("class_type", "Node")),
                title=str((node.get("_meta") or {}).get("title") or node.get("class_type") or node_id),
                summary=_node_summary(node),
            )
            for node_id, node in graph.items()
        ]
        return CreatorWorkflowGraph(id=template["id"], label=template["label"], nodes=nodes, raw=graph)

    # -- gpus ---------------------------------------------------------------

    def gpus(self) -> list[CreatorLabGpu]:
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=index,name,memory.total,memory.used,utilization.gpu,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=6,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        gpus: list[CreatorLabGpu] = []
        for line in result.stdout.strip().splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 6:
                continue
            gpus.append(
                CreatorLabGpu(
                    index=_int(parts[0]) or 0,
                    name=parts[1],
                    memory_total_mb=_int(parts[2]),
                    memory_used_mb=_int(parts[3]),
                    utilization=_int(parts[4]),
                    temperature=_int(parts[5]),
                )
            )
        return gpus

    def training_available(self) -> bool:
        return (Path("/srv/edison-data/training/sd-scripts/.venv/bin/python")).exists()

    # -- VLM critique -------------------------------------------------------

    def vlm_critique(self, image_bytes: bytes, prompt: str, question: str | None = None) -> CreatorVlmCritique:
        if not image_bytes:
            return CreatorVlmCritique(status="error", notes="No image to critique.")
        guard = creator_guard_reason(f"{prompt or ''} {question or ''}")
        if guard:
            return CreatorVlmCritique(status="error", notes=guard)
        encoded = base64.b64encode(image_bytes).decode("ascii")
        instruction = _vlm_instruction(prompt, question)
        for model in VISION_MODELS:
            try:
                response = httpx.post(
                    f"{OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": instruction, "images": [encoded]}],
                        "stream": False,
                        "format": "json",
                        # Bound the context window: qwen2.5-VL's default context plus image
                        # tokens overflows the KV-cache allocation ("failed to commit memory").
                        "options": {"temperature": 0.2, "num_predict": 500, "num_ctx": 8192},
                    },
                    timeout=180.0,
                )
            except httpx.HTTPError:
                continue
            if response.status_code == 404:
                continue
            if response.status_code >= 400:
                return CreatorVlmCritique(status="error", notes=f"Vision model error ({response.status_code}).", model_id=model)
            content = (response.json().get("message") or {}).get("content") or ""
            return _parse_vlm_payload(content, model)
        return CreatorVlmCritique(
            status="unavailable",
            notes="No local vision model is reachable. Ensure the qwen2.5-VL model is loaded in Ollama.",
        )

    # -- internals ----------------------------------------------------------

    def _checkpoint_exists(self, name: str) -> bool:
        if not self.comfyui_models_path:
            return name == DEFAULT_SDXL_BASE  # SDXL confirmed present on the box
        candidate = self.comfyui_models_path / "checkpoints" / name
        return candidate.exists()

    def _dataset_path(self, dataset_id: str) -> Path:
        return self._safe_child(self.datasets_dir, dataset_id)

    def _safe_child(self, parent: Path, name: str) -> Path:
        candidate = (parent / name).resolve()
        parent_resolved = parent.resolve()
        if parent_resolved not in candidate.parents and candidate != parent_resolved:
            raise CreatorLabError("Invalid path.", status_code=400)
        return candidate

    def _load_dataset(self, path: Path, *, include_images: bool) -> CreatorLabDataset | None:
        if not path.is_dir():
            return None
        config = self._read_dataset_config(path)
        if config is None:
            return None
        images_dir = path / "images"
        image_files = sorted(
            [p for p in images_dir.glob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]
        ) if images_dir.exists() else []
        images: list[CreatorLabImage] = []
        if include_images:
            for image_path in image_files:
                images.append(
                    CreatorLabImage(
                        id=image_path.name,
                        filename=image_path.name,
                        url=f"/api/v1/creator-lab/datasets/{config['id']}/images/{image_path.name}",
                        size_bytes=image_path.stat().st_size,
                    )
                )
        return CreatorLabDataset(
            id=config["id"],
            name=config["name"],
            trigger_token=config.get("trigger_token") or "creator_ai",
            lora_type=config.get("lora_type") or "sdxl",
            base_model=config.get("base_model"),
            workflow=config.get("workflow"),
            notes=config.get("notes"),
            status="ready" if image_files else "empty",
            image_count=len(image_files),
            created_at=config.get("created_at"),
            images=images,
        )

    def _read_dataset_config(self, path: Path) -> dict | None:
        config_path = path / "dataset.json"
        if not config_path.exists():
            return None
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict) or "id" not in data or "name" not in data:
            return None
        return data

    def _write_dataset_config(self, path: Path, config: dict) -> None:
        (path / "dataset.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    def _read_lab(self) -> dict:
        if not self.lab_file.exists():
            return {}
        try:
            data = json.loads(self.lab_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_lab(self, selection: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.lab_file.write_text(json.dumps(selection, indent=2), encoding="utf-8")

    def _make_dataset_id(self, name: str) -> str:
        slug = _slug_token(name)[:40] or "dataset"
        digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:6]
        return f"{slug}_{digest}"

    def _unique_image_path(self, images_dir: Path, filename: str) -> Path:
        stem = re.sub(r"[^a-zA-Z0-9._-]", "_", Path(filename).stem)[:60] or "image"
        suffix = Path(filename).suffix.lower()
        candidate = images_dir / f"{stem}{suffix}"
        counter = 1
        while candidate.exists():
            candidate = images_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        return candidate


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug_token(value: str) -> str:
    token = "".join(char.lower() if char.isalnum() else "_" for char in value)
    token = "_".join(part for part in token.split("_") if part)
    return token or "creator_ai"


def _int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _node_summary(node: dict) -> str:
    inputs = node.get("inputs") or {}
    parts = []
    for key, value in inputs.items():
        if isinstance(value, (str, int, float, bool)):
            text = str(value)
            if len(text) > 48:
                text = text[:45] + "..."
            parts.append(f"{key}={text}")
    return ", ".join(parts[:4])


def _vlm_instruction(prompt: str, question: str | None) -> str:
    target = prompt.strip() or "(no prompt provided)"
    extra = f"\nAlso answer this specifically: {question.strip()}" if question and question.strip() else ""
    return (
        "You are a strict visual QA reviewer for an AI image generator. Look at the image and judge how well it "
        f"matches the requested prompt.\nRequested prompt: \"{target}\"{extra}\n\n"
        "Respond with ONLY a JSON object: {\"score\": 0-100 integer for prompt match, \"matches\": true/false, "
        "\"verdict\": short phrase, \"notes\": 1-2 sentence critique of quality/anatomy/artifacts, "
        "\"suggestions\": [up to 3 short concrete fixes]}. Be honest and specific."
    )


def _parse_vlm_payload(content: str, model: str) -> CreatorVlmCritique:
    data = _first_json(content)
    if not isinstance(data, dict):
        return CreatorVlmCritique(status="ok", verdict="reviewed", notes=content.strip()[:600] or None, model_id=model)
    score = _int(str(data.get("score"))) if data.get("score") is not None else None
    if score is not None:
        score = max(0, min(100, score))
    suggestions = data.get("suggestions")
    suggestion_list = [str(item).strip()[:200] for item in suggestions if str(item).strip()][:3] if isinstance(suggestions, list) else []
    matches = data.get("matches")
    if matches is None and score is not None:
        matches = score >= 70
    return CreatorVlmCritique(
        status="ok",
        score=score,
        matches=bool(matches) if matches is not None else None,
        verdict=str(data.get("verdict") or "").strip()[:120] or None,
        notes=str(data.get("notes") or "").strip()[:600] or None,
        suggestions=suggestion_list,
        model_id=model,
    )


def _first_json(content: str) -> dict | None:
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _sdxl_graph(with_lora: bool) -> dict:
    model_ref = ["10", 0] if with_lora else ["4", 0]
    clip_ref = ["10", 1] if with_lora else ["4", 1]
    graph: dict = {
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": DEFAULT_SDXL_BASE},
            "_meta": {"title": "Load SDXL Checkpoint"},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "{positive}", "clip": clip_ref},
            "_meta": {"title": "Positive Prompt"},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "{negative}", "clip": clip_ref},
            "_meta": {"title": "Negative Prompt"},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
            "_meta": {"title": "Empty Latent 1024x1024"},
        },
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 0,
                "steps": 30,
                "cfg": 6.5,
                "sampler_name": "dpmpp_2m_sde",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": model_ref,
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
            "_meta": {"title": "KSampler"},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            "_meta": {"title": "VAE Decode"},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "creator/persona", "images": ["8", 0]},
            "_meta": {"title": "Save Image"},
        },
    }
    if with_lora:
        graph["10"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": "{lora}",
                "strength_model": 0.85,
                "strength_clip": 0.85,
                "model": ["4", 0],
                "clip": ["4", 1],
            },
            "_meta": {"title": "Apply Persona LoRA"},
        }
    return graph


_BUILTIN_WORKFLOWS: dict = {
    "sdxl_txt2img_lora": {
        "id": "sdxl_txt2img_lora",
        "label": "SDXL Portrait + Persona LoRA",
        "kind": "image",
        "detail": "SDXL text-to-image with a persona LoRA slot. The main creator workflow.",
        "graph": _sdxl_graph(with_lora=True),
    },
    "sdxl_txt2img": {
        "id": "sdxl_txt2img",
        "label": "SDXL Portrait (no LoRA)",
        "kind": "image",
        "detail": "Plain SDXL text-to-image for base persona exploration before training.",
        "graph": _sdxl_graph(with_lora=False),
    },
    "wan_video_clip": {
        "id": "wan_video_clip",
        "label": "Wan 2.2 Short Clip",
        "kind": "video",
        "detail": "Short non-explicit persona motion clip via the Wan 2.2 5B model.",
        "graph": {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "wan2.2_ti2v_5B_fp16.safetensors"},
                "_meta": {"title": "Load Wan 2.2 5B"},
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "{positive}", "clip": ["1", 1]},
                "_meta": {"title": "Positive Prompt"},
            },
            "3": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": 832, "height": 480, "batch_size": 1},
                "_meta": {"title": "Empty Latent (video)"},
            },
            "4": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 0,
                    "steps": 24,
                    "cfg": 6.0,
                    "sampler_name": "uni_pc",
                    "scheduler": "simple",
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["2", 0],
                    "latent_image": ["3", 0],
                },
                "_meta": {"title": "KSampler"},
            },
            "5": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": "creator/clip", "images": ["4", 0]},
                "_meta": {"title": "Save Frames"},
            },
        },
    },
}

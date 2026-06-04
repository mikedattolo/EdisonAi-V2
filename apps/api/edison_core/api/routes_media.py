from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from edison_core.api.dependencies import (
    get_comfyui_client,
    get_conversation_store,
    get_generation_store,
    get_invokeai_client,
    get_media_orchestrator,
    get_modly_client,
    get_wan22_client,
)
from edison_core.schemas import (
    ArtifactCreate,
    ArtifactKind,
    JobCreate,
    JobRecord,
    JobStatus,
    JobType,
    MediaJobDeliveryRequest,
    MediaGenerationMode,
    MediaGenerationModeRecord,
    MediaGenerationRequest,
    MediaSystemStatus,
    MessageCreate,
    MessageRecord,
    MessageRole,
)
from edison_core.services.comfyui_client import ComfyUIClient
from edison_core.services.conversation_store import ConversationNotFoundError, ConversationStore
from edison_core.services.generation_store import GenerationStore, JobNotFoundError
from edison_core.services.invokeai_client import InvokeAIClient
from edison_core.services.media_orchestrator import MediaOrchestrator
from edison_core.services.modly_client import ModlyClient
from edison_core.services.wan22_client import Wan22Client


router = APIRouter(prefix="/api/v1/media", tags=["media"])


@router.get("/modes", response_model=list[MediaGenerationModeRecord])
def media_generation_modes() -> list[MediaGenerationModeRecord]:
    return _media_modes()


@router.get("/status", response_model=MediaSystemStatus)
def media_status(
    comfyui: ComfyUIClient = Depends(get_comfyui_client),
    invokeai: InvokeAIClient = Depends(get_invokeai_client),
    wan22: Wan22Client = Depends(get_wan22_client),
    modly: ModlyClient = Depends(get_modly_client),
    store: GenerationStore = Depends(get_generation_store),
) -> MediaSystemStatus:
    return MediaSystemStatus(
        comfyui=comfyui.status(),
        invokeai=invokeai.status(),
        wan22=wan22.status(),
        modly=modly.status(),
        job_counts=store.job_counts(),
    )


@router.post("/generate", response_model=JobRecord, status_code=status.HTTP_201_CREATED)
def generate_media(
    payload: MediaGenerationRequest,
    comfyui: ComfyUIClient = Depends(get_comfyui_client),
    invokeai: InvokeAIClient = Depends(get_invokeai_client),
    wan22: Wan22Client = Depends(get_wan22_client),
    modly: ModlyClient = Depends(get_modly_client),
    orchestrator: MediaOrchestrator = Depends(get_media_orchestrator),
    store: GenerationStore = Depends(get_generation_store),
) -> JobRecord:
    mode = _mode_record(payload.mode)
    if _is_planning_mode(payload.mode, payload.reference_artifact_id):
        return _create_planning_artifact_job(payload, mode, store, orchestrator.settings.artifact_root)

    job_payload = _job_from_generation_request(payload, mode)
    return create_media_job(job_payload, comfyui, invokeai, wan22, modly, orchestrator, store)


@router.post("/jobs", response_model=JobRecord, status_code=status.HTTP_201_CREATED)
def create_media_job(
    payload: JobCreate,
    comfyui: ComfyUIClient = Depends(get_comfyui_client),
    invokeai: InvokeAIClient = Depends(get_invokeai_client),
    wan22: Wan22Client = Depends(get_wan22_client),
    modly: ModlyClient = Depends(get_modly_client),
    orchestrator: MediaOrchestrator = Depends(get_media_orchestrator),
    store: GenerationStore = Depends(get_generation_store),
) -> JobRecord:
    selected_backend = _resolve_backend(payload)
    backend_status = _backend_status(selected_backend, comfyui, invokeai, wan22, modly)
    payload.backend = selected_backend
    payload.metadata = {
        **payload.metadata,
        "backend_status": backend_status.model_dump(mode="json"),
        "backend": selected_backend,
    }
    if backend_status.status != "ready":
        job = store.create_job(payload, status=JobStatus.SETUP_REQUIRED)
        store.add_event(
            job.id,
            JobStatus.SETUP_REQUIRED,
            backend_status.detail,
            {"base_url": backend_status.base_url, "backend": selected_backend},
        )
        return job
    return orchestrator.submit_job(payload, store)


@router.post("/jobs/{job_id}/sync", response_model=JobRecord)
def sync_media_job(
    job_id: str,
    orchestrator: MediaOrchestrator = Depends(get_media_orchestrator),
    store: GenerationStore = Depends(get_generation_store),
) -> JobRecord:
    return orchestrator.sync_job(job_id, store)


@router.post("/jobs/{job_id}/cancel", response_model=JobRecord)
def cancel_media_job(
    job_id: str,
    orchestrator: MediaOrchestrator = Depends(get_media_orchestrator),
    store: GenerationStore = Depends(get_generation_store),
) -> JobRecord:
    return orchestrator.cancel_job(job_id, store)


@router.post("/jobs/{job_id}/deliver", response_model=MessageRecord, status_code=status.HTTP_201_CREATED)
def deliver_media_job_to_chat(
    job_id: str,
    payload: MediaJobDeliveryRequest,
    store: GenerationStore = Depends(get_generation_store),
    conversations: ConversationStore = Depends(get_conversation_store),
) -> MessageRecord:
    try:
        job = store.get_job(job_id)
    except JobNotFoundError as error:
        raise HTTPException(status_code=404, detail="Job not found") from error

    conversation_id = payload.conversation_id or _string_metadata(job.metadata, "conversation_id")
    if not conversation_id:
        raise HTTPException(status_code=400, detail="No conversation id was provided for delivery.")
    if job.status != JobStatus.COMPLETE or not job.result_artifact_id:
        raise HTTPException(status_code=409, detail="Media job does not have a completed artifact yet.")

    existing_message_id = _string_metadata(job.metadata, "delivered_message_id")
    if existing_message_id:
        try:
            conversation = conversations.get_conversation(conversation_id)
        except ConversationNotFoundError as error:
            raise HTTPException(status_code=404, detail="Conversation not found") from error
        for message in conversation.messages:
            if message.id == existing_message_id:
                return message

    try:
        artifact = store.get_artifact(job.result_artifact_id)
    except JobNotFoundError as error:
        raise HTTPException(status_code=404, detail="Generated artifact not found") from error

    try:
        message = conversations.add_message(
            conversation_id,
            MessageCreate(
                role=MessageRole.ASSISTANT,
                content=f"Done. I generated {artifact.kind.value} output for {job.title}.",
                model=job.backend,
                metadata={
                    "delivery_type": "media_result",
                    "media_job": job.model_dump(mode="json"),
                    "artifacts": [artifact.model_dump(mode="json")],
                },
            ),
        )
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found") from error

    store.update_job_status(
        job.id,
        job.status,
        "Media result delivered to chat.",
        {"delivered_message_id": message.id, "conversation_id": conversation_id},
    )
    return message


def _resolve_backend(payload: JobCreate) -> str:
    requested = (payload.backend or "").strip().lower()
    if requested in {"comfyui", "invokeai", "wan22", "modly"}:
        return requested
    if payload.job_type == "video":
        return "wan22"
    if payload.job_type == "mesh":
        return "modly"
    return "comfyui"


def _backend_status(
    backend: str,
    comfyui: ComfyUIClient,
    invokeai: InvokeAIClient,
    wan22: Wan22Client,
    modly: ModlyClient,
):
    if backend == "invokeai":
        return invokeai.status()
    if backend == "wan22":
        return wan22.status()
    if backend == "modly":
        return modly.status()
    return comfyui.status()


def _string_metadata(payload: dict, key: str) -> str | None:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _media_modes() -> list[MediaGenerationModeRecord]:
    return [
        MediaGenerationModeRecord(
            id=MediaGenerationMode.IMAGE,
            label="Image",
            group="core",
            job_type=JobType.IMAGE,
            backend="comfyui",
            description="General Edison image generation through the configured image backend.",
            reference_supported=True,
            output_hint="Image artifact",
            prompt_hint="Describe the image, style, subject, and any constraints.",
        ),
        MediaGenerationModeRecord(
            id=MediaGenerationMode.MINECRAFT_TEXTURE,
            label="Minecraft Texture",
            group="minecraft",
            job_type=JobType.IMAGE,
            backend="comfyui",
            description="Pixel-art texture concepts for Minecraft 1.7.10 packs.",
            reference_supported=True,
            output_hint="Tileable texture image",
            prompt_hint="Name the block/item, resolution, palette, and whether it should tile.",
            metadata={"minecraft_version": "1.7.10", "recommended_sizes": [16, 32, 64]},
        ),
        MediaGenerationModeRecord(
            id=MediaGenerationMode.MINECRAFT_MODEL,
            label="Minecraft Model",
            group="minecraft",
            job_type=JobType.CODE,
            backend="minecraft-suite",
            description="Blockbench-ready model specifications and optional image-to-mesh handoff when a reference is attached.",
            reference_supported=True,
            output_hint="Model specification or mesh job",
            prompt_hint="Describe entity/block shape, texture slots, scale, and 1.7.10 mod target.",
            metadata={"minecraft_version": "1.7.10", "editor": "Blockbench"},
        ),
        MediaGenerationModeRecord(
            id=MediaGenerationMode.MINECRAFT_WORLD,
            label="Minecraft World",
            group="minecraft",
            job_type=JobType.CODE,
            backend="minecraft-suite",
            description="World-generation design specs for biomes, structures, loot, and mod constraints.",
            reference_supported=False,
            output_hint="World design spec",
            prompt_hint="Describe biome, progression, terrain, POIs, and modpack constraints.",
            metadata={"minecraft_version": "1.7.10"},
        ),
        MediaGenerationModeRecord(
            id=MediaGenerationMode.MINECRAFT_STRUCTURE,
            label="Minecraft Structure",
            group="minecraft",
            job_type=JobType.CODE,
            backend="minecraft-suite",
            description="Structure build specs and schematic handoff notes.",
            reference_supported=True,
            output_hint="Structure blueprint spec",
            prompt_hint="Describe footprint, materials, rooms, redstone, and survival/build mode.",
            metadata={"minecraft_version": "1.7.10"},
        ),
        MediaGenerationModeRecord(
            id=MediaGenerationMode.MINECRAFT_TEXTURE_PACK,
            label="Minecraft Texture Pack",
            group="minecraft",
            job_type=JobType.CODE,
            backend="minecraft-suite",
            description="Texture-pack manifest, asset list, palette, and production plan.",
            reference_supported=True,
            output_hint="Texture pack production spec",
            prompt_hint="Describe theme, blocks/items/entities, resolution, and pack tone.",
            metadata={"minecraft_version": "1.7.10"},
        ),
        MediaGenerationModeRecord(
            id=MediaGenerationMode.PRODUCT_RENDER,
            label="Product Render",
            group="commerce",
            job_type=JobType.IMAGE,
            backend="comfyui",
            description="Clean product shots for ToyBox3D listings, thumbnails, and Shopify media.",
            reference_supported=True,
            output_hint="Product render image",
            prompt_hint="Describe the product, angle, material, color, and listing style.",
        ),
        MediaGenerationModeRecord(
            id=MediaGenerationMode.SOCIAL_MEDIA_CONTENT,
            label="Social Media Content",
            group="social",
            job_type=JobType.DOCUMENT,
            backend="media-planner",
            description="Social post copy, creative direction, and optional image prompt plan.",
            reference_supported=True,
            output_hint="Campaign content spec",
            prompt_hint="Describe platform, product/topic, tone, audience, and call to action.",
        ),
    ]


def _mode_record(mode: MediaGenerationMode) -> MediaGenerationModeRecord:
    return next(item for item in _media_modes() if item.id == mode)


def _job_from_generation_request(payload: MediaGenerationRequest, mode: MediaGenerationModeRecord) -> JobCreate:
    prompt = _prompt_for_mode(payload, mode)
    metadata = {
        **payload.metadata,
        "generation_mode": payload.mode.value,
        "mode_label": mode.label,
        "reference_artifact_id": payload.reference_artifact_id,
        "enhance_prompt": True,
    }
    if payload.reference_artifact_id:
        metadata["source_artifact_id"] = payload.reference_artifact_id
    return JobCreate(
        job_type=mode.job_type,
        title=payload.title or f"{mode.label}: {_title_from_prompt(payload.prompt)}",
        prompt=prompt,
        backend=mode.backend,
        source_artifact_id=payload.reference_artifact_id if mode.job_type == JobType.MESH else None,
        metadata=metadata,
    )


def _prompt_for_mode(payload: MediaGenerationRequest, mode: MediaGenerationModeRecord) -> str:
    prompt = " ".join(payload.prompt.split())
    if payload.mode == MediaGenerationMode.MINECRAFT_TEXTURE:
        return (
            f"Minecraft 1.7.10 pixel art texture, {prompt}. "
            "Tileable square game texture, crisp pixels, readable silhouette, no UI text, no watermark."
        )
    if payload.mode == MediaGenerationMode.PRODUCT_RENDER:
        return (
            f"Studio product render for a ToyBox3D Shopify listing, {prompt}. "
            "Clean background, accurate shape, printable plastic material, clear lighting, commercial thumbnail."
        )
    return prompt


def _is_planning_mode(mode: MediaGenerationMode, reference_artifact_id: str | None) -> bool:
    return mode in {
        MediaGenerationMode.MINECRAFT_MODEL,
        MediaGenerationMode.MINECRAFT_WORLD,
        MediaGenerationMode.MINECRAFT_STRUCTURE,
        MediaGenerationMode.MINECRAFT_TEXTURE_PACK,
        MediaGenerationMode.SOCIAL_MEDIA_CONTENT,
    }


def _create_planning_artifact_job(
    payload: MediaGenerationRequest,
    mode: MediaGenerationModeRecord,
    store: GenerationStore,
    artifact_root: Path,
) -> JobRecord:
    backend = "minecraft-suite" if mode.group == "minecraft" else "media-planner"
    job = store.create_job(
        JobCreate(
            job_type=mode.job_type,
            title=payload.title or f"{mode.label}: {_title_from_prompt(payload.prompt)}",
            prompt=payload.prompt,
            backend=backend,
            metadata={
                **payload.metadata,
                "generation_mode": payload.mode.value,
                "mode_label": mode.label,
                "reference_artifact_id": payload.reference_artifact_id,
            },
        ),
        status=JobStatus.GENERATING,
    )
    content = _planning_markdown(payload, mode)
    output_dir = artifact_root / backend / job.id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{payload.mode.value}-{uuid4().hex[:8]}.md"
    output_path.write_text(content, encoding="utf-8", newline="\n")
    artifact = store.create_artifact(
        ArtifactCreate(
            kind=ArtifactKind.DOCUMENT if mode.job_type == JobType.DOCUMENT else ArtifactKind.CODE,
            title=f"{mode.label} spec",
            path=output_path.relative_to(artifact_root.parent).as_posix(),
            mime_type="text/markdown",
            source_job_id=job.id,
            metadata={
                "generation_mode": payload.mode.value,
                "mode_label": mode.label,
                "reference_artifact_id": payload.reference_artifact_id,
            },
        )
    )
    return store.finalize_job_result(
        job.id,
        result_artifact_id=artifact.id,
        status=JobStatus.COMPLETE,
        message=f"{mode.label} planning artifact generated.",
        metadata={"result_artifact_id": artifact.id, "generation_mode": payload.mode.value},
    )


def _planning_markdown(payload: MediaGenerationRequest, mode: MediaGenerationModeRecord) -> str:
    prompt = payload.prompt.strip()
    reference = payload.reference_artifact_id or "None attached"
    if mode.group == "minecraft":
        sections = [
            f"# {mode.label} for Minecraft 1.7.10",
            f"Prompt: {prompt}",
            f"Reference artifact: {reference}",
            "## Asset Targets",
            "- Minecraft version: 1.7.10",
            "- Keep naming lowercase with underscores.",
            "- Prefer 16x or 32x textures unless the prompt requests otherwise.",
            "- Produce Blockbench/resource-pack handoff notes where applicable.",
            "## Build Notes",
            "- Define palette, scale, collision/visual bounds, and export target.",
            "- Track generated files in Edison artifacts before packaging.",
        ]
    else:
        sections = [
            f"# {mode.label}",
            f"Prompt: {prompt}",
            f"Reference artifact: {reference}",
            "## Content Plan",
            "- Generate the primary visual or campaign direction.",
            "- Include caption/copy variants, thumbnail guidance, and asset checklist.",
            "- Keep product naming and store-ready output metadata attached to the job.",
        ]
    return "\n\n".join(sections) + "\n"


def _title_from_prompt(prompt: str) -> str:
    title = " ".join(prompt.split())
    return f"{title[:53]}..." if len(title) > 56 else title or "Untitled"

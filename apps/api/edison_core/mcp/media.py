from __future__ import annotations

from typing import Any

from edison_core.config import load_settings
from edison_core.database import SQLiteDatabase
from edison_core.mcp.runtime import MCPServer, MCPTool, boolean_schema, integer_schema, object_schema, string_schema
from edison_core.schemas import JobCreate, JobStatus, JobType, MediaSystemStatus
from edison_core.services.comfyui_client import ComfyUIClient
from edison_core.services.generation_store import GenerationStore
from edison_core.services.invokeai_client import InvokeAIClient
from edison_core.services.media_orchestrator import MediaOrchestrator
from edison_core.services.modly_client import ModlyClient
from edison_core.services.wan22_client import Wan22Client


def create_server(
    store: GenerationStore | None = None,
    orchestrator: MediaOrchestrator | None = None,
    comfyui: ComfyUIClient | None = None,
    invokeai: InvokeAIClient | None = None,
    wan22: Wan22Client | None = None,
    modly: ModlyClient | None = None,
) -> MCPServer:
    settings = orchestrator.settings if orchestrator is not None else load_settings()
    media_store = store or _default_store()
    comfyui_client = comfyui or ComfyUIClient(settings.comfyui_base_url, settings.comfyui_timeout_seconds)
    invokeai_client = invokeai or InvokeAIClient(settings.invokeai_base_url, settings.invokeai_timeout_seconds)
    wan22_client = wan22 or Wan22Client(settings.wan22_base_url, settings.wan22_timeout_seconds)
    modly_client = modly or ModlyClient(settings.modly_base_url, settings.modly_timeout_seconds)
    media = orchestrator or MediaOrchestrator(
        settings,
        comfyui_client,
        invokeai_client,
        wan22_client,
        modly_client,
    )

    return MCPServer(
        name="edison-media",
        version="0.1.0",
        tools=[
            MCPTool(
                name="media.status",
                description="Return Edison media backend health and generation job counts.",
                input_schema=object_schema(),
                handler=lambda _: MediaSystemStatus(
                    comfyui=comfyui_client.status(),
                    invokeai=invokeai_client.status(),
                    wan22=wan22_client.status(),
                    modly=modly_client.status(),
                    job_counts=media_store.job_counts(),
                ),
            ),
            MCPTool(
                name="media.create_job",
                description="Create an Edison media job and submit it when the selected backend is ready.",
                input_schema=object_schema(
                    {
                        "job_type": string_schema("Media job type: image, image_edit, video, mesh, audio, document, code, or system", "image"),
                        "title": string_schema("Human-readable job title"),
                        "prompt": string_schema("Generation prompt", ""),
                        "backend": string_schema("Backend to use: auto, comfyui, invokeai, wan22, modly", "auto"),
                        "source_artifact_id": string_schema("Optional source artifact id", ""),
                        "submit": boolean_schema("Submit immediately if the backend is ready", True),
                        "metadata": {
                            "type": "object",
                            "description": "Optional backend metadata such as workflow, width, height, seed, or conversation_id.",
                            "additionalProperties": True,
                            "default": {},
                        },
                    },
                    ["title"],
                ),
                handler=lambda args: _create_job(args, media_store, media, comfyui_client, invokeai_client, wan22_client, modly_client),
            ),
            MCPTool(
                name="media.jobs",
                description="List recent Edison media jobs.",
                input_schema=object_schema(
                    {
                        "job_type": string_schema("Optional job type filter", ""),
                        "status": string_schema("Optional job status filter", ""),
                        "limit": integer_schema("Maximum jobs to return", 20, 1, 100),
                    }
                ),
                handler=lambda args: media_store.list_jobs(
                    job_type=_optional_job_type(args.get("job_type")),
                    status=_optional_job_status(args.get("status")),
                    limit=int(args.get("limit", 20)),
                ),
            ),
            MCPTool(
                name="media.sync_job",
                description="Poll a submitted media job and collect completed artifacts when available.",
                input_schema=object_schema({"job_id": string_schema("Edison media job id")}, ["job_id"]),
                handler=lambda args: media.sync_job(str(args["job_id"]), media_store),
            ),
            MCPTool(
                name="media.cancel_job",
                description="Cancel an Edison media job.",
                input_schema=object_schema({"job_id": string_schema("Edison media job id")}, ["job_id"]),
                handler=lambda args: media.cancel_job(str(args["job_id"]), media_store),
            ),
            MCPTool(
                name="artifacts.list",
                description="List recent Edison-generated artifacts for inline chat/gallery display.",
                input_schema=object_schema({"limit": integer_schema("Maximum artifacts to return", 20, 1, 100)}),
                handler=lambda args: media_store.list_artifacts(limit=int(args.get("limit", 20))),
            ),
            MCPTool(
                name="artifacts.get",
                description="Return a single Edison artifact by id.",
                input_schema=object_schema({"artifact_id": string_schema("Edison artifact id")}, ["artifact_id"]),
                handler=lambda args: media_store.get_artifact(str(args["artifact_id"])),
            ),
        ],
    )


def _create_job(
    args: dict[str, Any],
    store: GenerationStore,
    orchestrator: MediaOrchestrator,
    comfyui: ComfyUIClient,
    invokeai: InvokeAIClient,
    wan22: Wan22Client,
    modly: ModlyClient,
):
    metadata = args.get("metadata") if isinstance(args.get("metadata"), dict) else {}
    source_artifact_id = _optional_string(args.get("source_artifact_id"))
    if source_artifact_id:
        metadata = {**metadata, "source_artifact_id": source_artifact_id}
    payload = JobCreate(
        job_type=JobType(str(args.get("job_type") or JobType.IMAGE.value)),
        title=str(args["title"]),
        prompt=_optional_string(args.get("prompt")),
        backend=str(args.get("backend") or "auto"),
        source_artifact_id=source_artifact_id,
        metadata=metadata,
    )
    selected_backend = _resolve_backend(payload)
    backend_status = _backend_status(selected_backend, comfyui, invokeai, wan22, modly)
    payload.backend = selected_backend
    payload.metadata = {
        **payload.metadata,
        "backend": selected_backend,
        "backend_status": backend_status.model_dump(mode="json"),
    }

    if args.get("submit", True) is False:
        return store.create_job(payload, status=JobStatus.QUEUED)
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


def _resolve_backend(payload: JobCreate) -> str:
    requested = (payload.backend or "").strip().lower()
    if requested in {"comfyui", "invokeai", "wan22", "modly"}:
        return requested
    if payload.job_type == JobType.VIDEO:
        return "wan22"
    if payload.job_type == JobType.MESH:
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


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _optional_job_type(value: Any) -> JobType | None:
    text = _optional_string(value)
    return JobType(text) if text else None


def _optional_job_status(value: Any) -> JobStatus | None:
    text = _optional_string(value)
    return JobStatus(text) if text else None


def _default_store() -> GenerationStore:
    settings = load_settings()
    store = GenerationStore(SQLiteDatabase(settings.database_path))
    store.initialize()
    return store


def main() -> None:
    create_server().serve_stdio()


if __name__ == "__main__":
    main()

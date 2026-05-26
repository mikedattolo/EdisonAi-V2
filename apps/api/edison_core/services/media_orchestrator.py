from __future__ import annotations

import json
import mimetypes
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from edison_core.config import EdisonSettings
from edison_core.schemas import ArtifactCreate, ArtifactKind, JobCreate, JobRecord, JobStatus
from edison_core.services.comfyui_client import ComfyUIClient
from edison_core.services.generation_store import GenerationStore, JobNotFoundError
from edison_core.services.invokeai_client import InvokeAIClient
from edison_core.services.modly_client import ModlyClient
from edison_core.services.wan22_client import Wan22Client


class MediaExecutionError(ValueError):
    pass


@dataclass
class BackendSubmission:
    remote_job_id: str | None = None
    outputs: list[dict[str, Any]] | None = None
    status: str = "queued"
    detail: str = "Job submitted"
    metadata: dict[str, Any] | None = None


class MediaOrchestrator:
    def __init__(
        self,
        settings: EdisonSettings,
        comfyui: ComfyUIClient,
        invokeai: InvokeAIClient,
        wan22: Wan22Client,
        modly: ModlyClient,
    ) -> None:
        self.settings = settings
        self.comfyui = comfyui
        self.invokeai = invokeai
        self.wan22 = wan22
        self.modly = modly

    def submit_job(self, payload: JobCreate, store: GenerationStore) -> JobRecord:
        job = store.create_job(payload, status=JobStatus.LOADING)
        try:
            submission = self._submit(payload.backend, payload, store)
        except Exception as error:
            return store.update_job_status(job.id, JobStatus.ERROR, f"Media submit failed: {error}", {"backend": payload.backend})

        if submission.outputs:
            completed_job = self._collect_outputs(job, submission.outputs, store, submission.detail)
            return completed_job

        metadata = {
            **(submission.metadata or {}),
            "backend": payload.backend,
            "remote_job_id": submission.remote_job_id,
        }
        return store.update_job_status(job.id, JobStatus.GENERATING, submission.detail, metadata)

    def sync_job(self, job_id: str, store: GenerationStore) -> JobRecord:
        job = store.get_job(job_id)
        remote_job_id = _string_metadata(job.metadata, "remote_job_id")
        if not remote_job_id:
            return job

        try:
            submission = self._poll(job.backend, remote_job_id, job.metadata)
        except Exception as error:
            return store.update_job_status(job.id, JobStatus.ERROR, f"Media poll failed: {error}", {"backend": job.backend})

        if submission.outputs:
            return self._collect_outputs(job, submission.outputs, store, submission.detail)

        next_status = JobStatus.GENERATING if submission.status in {"queued", "loading", "generating", "encoding"} else JobStatus.ERROR
        return store.update_job_status(job.id, next_status, submission.detail, submission.metadata or {})

    def cancel_job(self, job_id: str, store: GenerationStore) -> JobRecord:
        job = store.get_job(job_id)
        remote_job_id = _string_metadata(job.metadata, "remote_job_id")
        if remote_job_id:
            try:
                self._cancel(job.backend, remote_job_id, job.metadata)
            except Exception as error:
                return store.update_job_status(job.id, JobStatus.ERROR, f"Media cancel failed: {error}", {"backend": job.backend})
        return store.update_job_status(job.id, JobStatus.CANCELLED, "Media job cancelled", {"backend": job.backend})

    def _submit(self, backend: str, payload: JobCreate, store: GenerationStore) -> BackendSubmission:
        if backend == "comfyui":
            return self._submit_comfyui(payload)
        if backend == "invokeai":
            return self._submit_generic(self.invokeai.base_url, payload, default_submit_path="/generate")
        if backend == "wan22":
            return self._submit_generic(self.wan22.base_url, payload, default_submit_path="/generate")
        if backend == "modly":
            return self._submit_modly(payload, store)
        raise MediaExecutionError(f"Unsupported media backend: {backend}")

    def _poll(self, backend: str, remote_job_id: str, metadata: dict[str, Any]) -> BackendSubmission:
        if backend == "comfyui":
            return self._poll_comfyui(remote_job_id)
        if backend == "modly":
            return self._poll_modly(remote_job_id)
        base_url = self._base_url_for(backend)
        return self._poll_generic(base_url, remote_job_id, metadata)

    def _cancel(self, backend: str, remote_job_id: str, metadata: dict[str, Any]) -> None:
        if backend == "comfyui":
            return
        base_url = self._base_url_for(backend)
        self._cancel_generic(base_url, remote_job_id, metadata)

    def _submit_comfyui(self, payload: JobCreate) -> BackendSubmission:
        if not self.comfyui.base_url:
            raise MediaExecutionError("ComfyUI base URL is not configured")
        workflow = payload.metadata.get("workflow")
        if not isinstance(workflow, dict) or not workflow:
            if payload.job_type.value not in {"image", "image_edit"}:
                raise MediaExecutionError("ComfyUI submissions require metadata.workflow with an API prompt graph")
            workflow = _default_sdxl_workflow(payload)
        body = {"prompt": workflow}
        response = self._post_json(self.comfyui.base_url, "/prompt", body)
        prompt_id = str(response.get("prompt_id") or response.get("prompt_id", ""))
        if not prompt_id:
            raise MediaExecutionError("ComfyUI did not return a prompt_id")
        return BackendSubmission(remote_job_id=prompt_id, status="queued", detail="ComfyUI prompt submitted", metadata={"prompt_id": prompt_id})

    def _submit_modly(self, payload: JobCreate, store: GenerationStore) -> BackendSubmission:
        if not self.modly.base_url:
            raise MediaExecutionError("Modly base URL is not configured")
        source_artifact_id = payload.source_artifact_id or _string_metadata(payload.metadata, "source_artifact_id")
        if not source_artifact_id:
            raise MediaExecutionError("Modly mesh jobs require source_artifact_id for an image artifact")
        source_artifact = store.get_artifact(source_artifact_id)
        if source_artifact.kind != ArtifactKind.IMAGE:
            raise MediaExecutionError("Modly mesh jobs require an image artifact as input")
        source_path = _artifact_file_path(self.settings.artifact_root.parent, source_artifact.path)
        if not source_path.exists():
            raise MediaExecutionError(f"Source artifact file was not found: {source_artifact.path}")

        metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
        model_params = metadata.get("params") if isinstance(metadata.get("params"), dict) else {}
        model_params = dict(model_params)
        for key in ("num_inference_steps", "octree_resolution", "guidance_scale", "seed"):
            if key in metadata:
                model_params[key] = metadata[key]

        fields = {
            "model_id": str(metadata.get("model_id") or "hunyuan3d-mini-fast/generate"),
            "collection": str(metadata.get("collection") or "Edison Chat"),
            "remesh": str(metadata.get("remesh") or "quad"),
            "enable_texture": str(bool(metadata.get("enable_texture", False))).lower(),
            "texture_resolution": str(_int_metadata(metadata, "texture_resolution", 1024, minimum=256, maximum=4096)),
            "params": json.dumps(model_params),
        }
        response = self._post_multipart(
            self.modly.base_url,
            "/generate/from-image",
            fields,
            source_path,
            source_artifact.mime_type or _mime_from_suffix(source_path.suffix),
        )
        remote_job_id = _string_from_response(response, ["job_id", "id"])
        if not remote_job_id:
            raise MediaExecutionError("Modly did not return a job_id")
        return BackendSubmission(
            remote_job_id=remote_job_id,
            status="queued",
            detail="Modly image-to-3D job submitted",
            metadata={
                "remote_job_id": remote_job_id,
                "status_path_template": "/generate/status/{job_id}",
                "cancel_path_template": "/generate/cancel/{job_id}",
                "source_artifact_id": source_artifact_id,
                "model_id": fields["model_id"],
            },
        )

    def _poll_comfyui(self, remote_job_id: str) -> BackendSubmission:
        if not self.comfyui.base_url:
            raise MediaExecutionError("ComfyUI base URL is not configured")
        response = self._get_json(self.comfyui.base_url, f"/history/{remote_job_id}")
        job_payload = response.get(remote_job_id)
        if not isinstance(job_payload, dict):
            return BackendSubmission(remote_job_id=remote_job_id, status="generating", detail="ComfyUI job still running")

        outputs = []
        output_nodes = job_payload.get("outputs")
        if isinstance(output_nodes, dict):
            for node_output in output_nodes.values():
                if not isinstance(node_output, dict):
                    continue
                for key in ("images", "gifs", "videos"):
                    items = node_output.get(key)
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                outputs.append({**item, "kind": key[:-1] if key.endswith("s") else key})
        if outputs:
            return BackendSubmission(remote_job_id=remote_job_id, outputs=outputs, status="complete", detail="ComfyUI job completed")
        status_info = job_payload.get("status") if isinstance(job_payload.get("status"), dict) else {}
        if status_info.get("status_str") == "error":
            return BackendSubmission(remote_job_id=remote_job_id, status="error", detail="ComfyUI job failed", metadata=status_info)
        return BackendSubmission(remote_job_id=remote_job_id, status="generating", detail="ComfyUI job has no outputs yet")

    def _poll_modly(self, remote_job_id: str) -> BackendSubmission:
        if not self.modly.base_url:
            raise MediaExecutionError("Modly base URL is not configured")
        response = self._get_json(self.modly.base_url, f"/generate/status/{remote_job_id}")
        status_value = str(response.get("status") or "running").lower()
        if status_value == "done" and response.get("output_url"):
            output_url = str(response["output_url"])
            if output_url.startswith("/"):
                output_url = f"{self.modly.base_url}{output_url}"
            return BackendSubmission(
                remote_job_id=remote_job_id,
                outputs=[{"download_url": output_url, "kind": "mesh"}],
                status="complete",
                detail="Modly mesh job completed",
                metadata=response,
            )
        if status_value == "error":
            return BackendSubmission(
                remote_job_id=remote_job_id,
                status="error",
                detail=str(response.get("error") or "Modly mesh job failed"),
                metadata=response,
            )
        if status_value == "cancelled":
            return BackendSubmission(
                remote_job_id=remote_job_id,
                status="error",
                detail="Modly mesh job was cancelled",
                metadata=response,
            )
        detail = str(response.get("step") or f"Modly mesh job {status_value}")
        return BackendSubmission(remote_job_id=remote_job_id, status="generating", detail=detail, metadata=response)

    def _submit_generic(self, base_url: str | None, payload: JobCreate, default_submit_path: str) -> BackendSubmission:
        if not base_url:
            raise MediaExecutionError(f"{payload.backend} base URL is not configured")
        submit_path = _string_metadata(payload.metadata, "submit_path") or default_submit_path
        submit_payload = payload.metadata.get("submit_payload")
        if not isinstance(submit_payload, dict):
            submit_payload = {
                "prompt": payload.prompt,
                "title": payload.title,
                "job_type": payload.job_type.value,
                **payload.metadata,
            }
        response = self._post_json(base_url, submit_path, submit_payload)
        outputs = _extract_outputs(response)
        remote_job_id = _string_from_response(response, ["job_id", "id", "task_id", "batch_id"])
        detail = str(response.get("detail") or response.get("message") or f"{payload.backend} job submitted")
        return BackendSubmission(remote_job_id=remote_job_id, outputs=outputs or None, status="queued", detail=detail, metadata=response if isinstance(response, dict) else {})

    def _poll_generic(self, base_url: str | None, remote_job_id: str, metadata: dict[str, Any]) -> BackendSubmission:
        if not base_url:
            raise MediaExecutionError("Media backend base URL is not configured")
        template = _string_metadata(metadata, "status_path_template") or "/jobs/{job_id}"
        status_path = template.format(job_id=remote_job_id)
        response = self._get_json(base_url, status_path)
        outputs = _extract_outputs(response)
        status_value = str(response.get("status") or response.get("state") or "generating").lower()
        detail = str(response.get("detail") or response.get("message") or f"{status_value} via backend poll")
        return BackendSubmission(
            remote_job_id=remote_job_id,
            outputs=outputs or None,
            status=status_value,
            detail=detail,
            metadata=response if isinstance(response, dict) else {},
        )

    def _cancel_generic(self, base_url: str | None, remote_job_id: str, metadata: dict[str, Any]) -> None:
        if not base_url:
            raise MediaExecutionError("Media backend base URL is not configured")
        template = _string_metadata(metadata, "cancel_path_template") or "/jobs/{job_id}/cancel"
        cancel_path = template.format(job_id=remote_job_id)
        self._post_json(base_url, cancel_path, {})

    def _collect_outputs(
        self,
        job: JobRecord,
        outputs: list[dict[str, Any]],
        store: GenerationStore,
        detail: str,
    ) -> JobRecord:
        last_artifact_id: str | None = None
        saved_paths: list[str] = []
        for index, output in enumerate(outputs, start=1):
            artifact = self._save_output_artifact(job, output, index, store)
            last_artifact_id = artifact.id
            saved_paths.append(artifact.path)
        return store.finalize_job_result(
            job.id,
            result_artifact_id=last_artifact_id,
            status=JobStatus.COMPLETE,
            message=detail,
            metadata={"artifact_paths": saved_paths, "backend": job.backend},
        )

    def _save_output_artifact(self, job: JobRecord, output: dict[str, Any], index: int, store: GenerationStore):
        if job.backend == "comfyui":
            content, mime_type, suffix = self._download_comfyui_output(output)
        else:
            content, mime_type, suffix = self._download_generic_output(output)

        artifact_kind = _artifact_kind_for_job(job.job_type.value)
        relative_path = self._write_artifact_file(job, index, content, suffix)
        return store.create_artifact(
            ArtifactCreate(
                kind=artifact_kind,
                title=f"{job.title} #{index}",
                path=relative_path,
                mime_type=mime_type,
                source_job_id=job.id,
                metadata={"backend": job.backend, "output": output},
            )
        )

    def _download_comfyui_output(self, output: dict[str, Any]) -> tuple[bytes, str, str]:
        if not self.comfyui.base_url:
            raise MediaExecutionError("ComfyUI base URL is not configured")
        filename = str(output.get("filename") or "")
        if not filename:
            raise MediaExecutionError("ComfyUI output is missing filename")
        subfolder = str(output.get("subfolder") or "")
        folder_type = str(output.get("type") or "output")
        query = f"?filename={filename}&subfolder={subfolder}&type={folder_type}"
        content, content_type = self._get_bytes(self.comfyui.base_url, f"/view{query}")
        suffix = Path(filename).suffix or _suffix_from_mime(content_type)
        return content, content_type or _mime_from_suffix(suffix), suffix

    def _download_generic_output(self, output: dict[str, Any]) -> tuple[bytes, str, str]:
        url = _string_from_dict(output, ["download_url", "url", "output_url"])
        if not url:
            raise MediaExecutionError("Backend output did not include a downloadable URL")
        parsed = urlparse(url)
        suffix = Path(parsed.path).suffix
        content, content_type = self._get_bytes_absolute(url)
        suffix = suffix or _suffix_from_mime(content_type)
        return content, content_type or _mime_from_suffix(suffix), suffix

    def _write_artifact_file(self, job: JobRecord, index: int, content: bytes, suffix: str) -> str:
        job_dir = self.settings.artifact_root / job.backend / job.id
        job_dir.mkdir(parents=True, exist_ok=True)
        filename = f"output-{index}{suffix or '.bin'}"
        path = job_dir / filename
        path.write_bytes(content)
        return path.relative_to(self.settings.artifact_root.parent).as_posix()

    def _base_url_for(self, backend: str) -> str | None:
        if backend == "invokeai":
            return self.invokeai.base_url
        if backend == "wan22":
            return self.wan22.base_url
        if backend == "modly":
            return self.modly.base_url
        return self.comfyui.base_url

    def _post_json(self, base_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(f"{base_url.rstrip('/')}{path}", json=payload)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}

    def _post_multipart(
        self,
        base_url: str,
        path: str,
        fields: dict[str, str],
        file_path: Path,
        mime_type: str,
    ) -> dict[str, Any]:
        with file_path.open("rb") as file_handle:
            files = {"image": (file_path.name, file_handle, mime_type)}
            with httpx.Client(timeout=60.0) as client:
                response = client.post(f"{base_url.rstrip('/')}{path}", data=fields, files=files)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}

    def _get_json(self, base_url: str, path: str) -> dict[str, Any]:
        with httpx.Client(timeout=60.0) as client:
            response = client.get(f"{base_url.rstrip('/')}{path}")
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}

    def _get_bytes(self, base_url: str, path: str) -> tuple[bytes, str]:
        with httpx.Client(timeout=120.0) as client:
            response = client.get(f"{base_url.rstrip('/')}{path}")
        response.raise_for_status()
        return response.content, response.headers.get("content-type", "application/octet-stream")

    def _get_bytes_absolute(self, url: str) -> tuple[bytes, str]:
        with httpx.Client(timeout=120.0) as client:
            response = client.get(url)
        response.raise_for_status()
        return response.content, response.headers.get("content-type", "application/octet-stream")



def _extract_outputs(response: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("outputs", "artifacts", "results", "files"):
        value = response.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    single_url = _string_from_response(response, ["download_url", "url", "output_url"])
    if single_url:
        return [{"download_url": single_url}]
    return []



def _artifact_kind_for_job(job_type: str) -> ArtifactKind:
    if job_type == "image" or job_type == "image_edit":
        return ArtifactKind.IMAGE
    if job_type == "video":
        return ArtifactKind.VIDEO
    if job_type == "mesh":
        return ArtifactKind.MESH
    if job_type == "audio":
        return ArtifactKind.AUDIO
    return ArtifactKind.OTHER



def _string_from_response(payload: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None



def _string_from_dict(payload: dict[str, Any], keys: list[str]) -> str | None:
    return _string_from_response(payload, keys)



def _string_metadata(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None



def _artifact_file_path(storage_root: Path, artifact_path: str) -> Path:
    path = Path(artifact_path)
    return path if path.is_absolute() else storage_root / path



def _suffix_from_mime(content_type: str | None) -> str:
    if not content_type:
        return ".bin"
    guess = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
    return guess or ".bin"



def _mime_from_suffix(suffix: str) -> str:
    return mimetypes.guess_type(f"file{suffix}")[0] or "application/octet-stream"


def _default_sdxl_workflow(payload: JobCreate) -> dict[str, Any]:
    metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
    checkpoint = str(metadata.get("checkpoint") or "sd_xl_base_1.0.safetensors")
    prompt = (payload.prompt or payload.title or "A clean Edison image generation").strip()
    positive_prompt = _enhanced_image_prompt(prompt, metadata)
    negative_prompt = str(
        metadata.get("negative_prompt")
        or "low quality, blurry, distorted, deformed, extra fingers, bad hands, bad anatomy, duplicate subject, cropped subject, watermark, signature, text artifacts"
    )
    width = _int_metadata(metadata, "width", 1024, minimum=256, maximum=1536)
    height = _int_metadata(metadata, "height", 1024, minimum=256, maximum=1536)
    steps = _int_metadata(metadata, "steps", 30, minimum=1, maximum=60)
    cfg = _float_metadata(metadata, "cfg", 6.5, minimum=1.0, maximum=20.0)
    sampler_name = str(metadata.get("sampler_name") or "dpmpp_2m")
    scheduler = str(metadata.get("scheduler") or "karras")
    seed = _int_metadata(metadata, "seed", random.randint(1, 2**31 - 1), minimum=0, maximum=2**63 - 1)
    filename_prefix = str(metadata.get("filename_prefix") or "edison_chat_image")

    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": positive_prompt, "clip": ["4", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["4", 1]},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": filename_prefix, "images": ["8", 0]},
        },
    }


def _enhanced_image_prompt(prompt: str, metadata: dict[str, Any]) -> str:
    if metadata.get("enhance_prompt") is False:
        return prompt
    clean = " ".join(prompt.split())
    if len(clean) > 260:
        return clean
    quality_suffix = (
        "high quality, coherent composition, clear subject, detailed but natural, "
        "balanced lighting, crisp focus, professional color grading"
    )
    if any(token in clean.lower() for token in ("photoreal", "cinematic", "illustration", "3d render", "logo")):
        return f"{clean}, {quality_suffix}"
    return f"{clean}, polished concept art, {quality_suffix}"


def _int_metadata(
    metadata: dict[str, Any],
    key: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(metadata.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _float_metadata(
    metadata: dict[str, Any],
    key: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    try:
        value = float(metadata.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))

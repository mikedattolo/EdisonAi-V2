from __future__ import annotations

import mimetypes
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
            submission = self._submit(payload.backend, payload)
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

    def _submit(self, backend: str, payload: JobCreate) -> BackendSubmission:
        if backend == "comfyui":
            return self._submit_comfyui(payload)
        if backend == "invokeai":
            return self._submit_generic(self.invokeai.base_url, payload, default_submit_path="/generate")
        if backend == "wan22":
            return self._submit_generic(self.wan22.base_url, payload, default_submit_path="/generate")
        if backend == "modly":
            return self._submit_generic(self.modly.base_url, payload, default_submit_path="/generate")
        raise MediaExecutionError(f"Unsupported media backend: {backend}")

    def _poll(self, backend: str, remote_job_id: str, metadata: dict[str, Any]) -> BackendSubmission:
        if backend == "comfyui":
            return self._poll_comfyui(remote_job_id)
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
            raise MediaExecutionError("ComfyUI submissions require metadata.workflow with an API prompt graph")
        body = {"prompt": workflow}
        response = self._post_json(self.comfyui.base_url, "/prompt", body)
        prompt_id = str(response.get("prompt_id") or response.get("prompt_id", ""))
        if not prompt_id:
            raise MediaExecutionError("ComfyUI did not return a prompt_id")
        return BackendSubmission(remote_job_id=prompt_id, status="queued", detail="ComfyUI prompt submitted", metadata={"prompt_id": prompt_id})

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



def _suffix_from_mime(content_type: str | None) -> str:
    if not content_type:
        return ".bin"
    guess = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
    return guess or ".bin"



def _mime_from_suffix(suffix: str) -> str:
    return mimetypes.guess_type(f"file{suffix}")[0] or "application/octet-stream"

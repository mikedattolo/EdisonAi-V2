from edison_core.config import EdisonSettings
from edison_core.database import SQLiteDatabase
from edison_core.schemas import ArtifactCreate, ArtifactKind, JobCreate, JobType
from edison_core.services.comfyui_client import ComfyUIClient
from edison_core.services.generation_store import GenerationStore
from edison_core.services.invokeai_client import InvokeAIClient
from edison_core.services.media_orchestrator import MediaOrchestrator
from edison_core.services.modly_client import ModlyClient
from edison_core.services.wan22_client import Wan22Client


def test_media_orchestrator_collects_comfyui_outputs(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        artifact_root=tmp_path / "artifacts",
        workspace_roots=[tmp_path],
        comfyui_base_url="http://comfyui.local",
        invokeai_base_url=None,
        wan22_base_url=None,
        modly_base_url=None,
    )
    store = GenerationStore(SQLiteDatabase(settings.database_path))
    store.initialize()

    orchestrator = MediaOrchestrator(
        settings,
        ComfyUIClient(settings.comfyui_base_url),
        InvokeAIClient(None),
        Wan22Client(None),
        ModlyClient(None),
    )

    orchestrator._post_json = lambda base_url, path, payload: {"prompt_id": "prompt-123"}  # type: ignore[method-assign]
    orchestrator._get_json = lambda base_url, path: {  # type: ignore[method-assign]
        "prompt-123": {
            "outputs": {
                "9": {
                    "images": [
                        {"filename": "sample.png", "subfolder": "", "type": "output"},
                    ]
                }
            }
        }
    }
    orchestrator._get_bytes = lambda base_url, path: (b"png-bytes", "image/png")  # type: ignore[method-assign]

    submitted = orchestrator.submit_job(
        JobCreate(
            job_type=JobType.IMAGE,
            title="Poster draft",
            backend="comfyui",
            metadata={"workflow": {"1": {"class_type": "EmptyLatentImage"}}},
        ),
        store,
    )
    assert submitted.status == "generating"

    synced = orchestrator.sync_job(submitted.id, store)
    assert synced.status == "complete"
    assert synced.result_artifact_id is not None

    artifact = store.get_artifact(synced.result_artifact_id)
    assert artifact.mime_type == "image/png"
    assert (tmp_path / artifact.path).exists()


def test_media_orchestrator_submits_modly_image_to_mesh(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        artifact_root=tmp_path / "artifacts",
        workspace_roots=[tmp_path],
        comfyui_base_url="",
        invokeai_base_url=None,
        wan22_base_url=None,
        modly_base_url="http://modly.local",
    )
    store = GenerationStore(SQLiteDatabase(settings.database_path))
    store.initialize()

    source_path = settings.artifact_root / "inputs" / "source.png"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"png-bytes")
    source_artifact = store.create_artifact(
        ArtifactCreate(
            kind=ArtifactKind.IMAGE,
            title="Source image",
            path=source_path.relative_to(settings.artifact_root.parent).as_posix(),
            mime_type="image/png",
        )
    )

    orchestrator = MediaOrchestrator(
        settings,
        ComfyUIClient(None),
        InvokeAIClient(None),
        Wan22Client(None),
        ModlyClient(settings.modly_base_url),
    )
    captured = {}

    def fake_post_multipart(base_url, path, fields, file_path, mime_type):
        captured.update(
            {
                "base_url": base_url,
                "path": path,
                "fields": fields,
                "file_path": file_path,
                "mime_type": mime_type,
            }
        )
        return {"job_id": "mesh-job-1"}

    orchestrator._post_multipart = fake_post_multipart  # type: ignore[method-assign]
    orchestrator._get_json = lambda base_url, path: {  # type: ignore[method-assign]
        "job_id": "mesh-job-1",
        "status": "done",
        "output_url": "/workspace/Edison%20Chat/output.glb",
    }
    orchestrator._get_bytes_absolute = lambda url: (b"glb-bytes", "model/gltf-binary")  # type: ignore[method-assign]

    submitted = orchestrator.submit_job(
        JobCreate(
            job_type=JobType.MESH,
            title="3D mesh",
            backend="modly",
            source_artifact_id=source_artifact.id,
            metadata={"model_id": "hunyuan3d-mini-fast/generate", "num_inference_steps": 5},
        ),
        store,
    )

    assert submitted.status == "generating"
    assert captured["path"] == "/generate/from-image"
    assert captured["file_path"] == source_path
    assert captured["fields"]["model_id"] == "hunyuan3d-mini-fast/generate"

    synced = orchestrator.sync_job(submitted.id, store)
    assert synced.status == "complete"
    assert synced.result_artifact_id is not None

    mesh_artifact = store.get_artifact(synced.result_artifact_id)
    assert mesh_artifact.kind == ArtifactKind.MESH
    assert (tmp_path / mesh_artifact.path).exists()

from edison_core.config import EdisonSettings
from edison_core.database import SQLiteDatabase
from edison_core.schemas import JobCreate, JobType
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

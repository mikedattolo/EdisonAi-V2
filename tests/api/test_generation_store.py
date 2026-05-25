from edison_core.database import SQLiteDatabase
from edison_core.schemas import ArtifactCreate, ArtifactKind, JobCreate, JobStatus, JobType
from edison_core.services.generation_store import GenerationStore


def test_generation_store_persists_jobs_events_and_artifacts(tmp_path):
    store = GenerationStore(SQLiteDatabase(tmp_path / "edison.sqlite3"))
    store.initialize()

    job = store.create_job(
        JobCreate(
            job_type=JobType.IMAGE,
            title="Generate logo concept",
            prompt="A clean Edison mark",
            backend="comfyui",
            metadata={"workflow": "flux-logo"},
        )
    )
    updated = store.update_job_status(job.id, JobStatus.SETUP_REQUIRED, "ComfyUI is offline")
    artifact = store.create_artifact(
        ArtifactCreate(
            kind=ArtifactKind.IMAGE,
            title="Logo concept",
            path="artifacts/logo.png",
            mime_type="image/png",
            source_job_id=job.id,
        )
    )

    loaded = store.get_job(job.id)
    events = store.list_events(job.id)
    artifacts = store.list_artifacts()

    assert updated.status == JobStatus.SETUP_REQUIRED
    assert loaded.metadata == {"workflow": "flux-logo"}
    assert [event.status for event in events] == [JobStatus.QUEUED, JobStatus.SETUP_REQUIRED]
    assert artifacts[0].id == artifact.id


def test_generation_store_counts_jobs_by_status(tmp_path):
    store = GenerationStore(SQLiteDatabase(tmp_path / "edison.sqlite3"))
    store.initialize()

    store.create_job(JobCreate(job_type=JobType.IMAGE, title="Queued image"))
    setup_job = store.create_job(JobCreate(job_type=JobType.VIDEO, title="Video setup"))
    store.update_job_status(setup_job.id, JobStatus.SETUP_REQUIRED, "Video backend missing")

    assert store.job_counts() == {"queued": 1, "setup_required": 1}
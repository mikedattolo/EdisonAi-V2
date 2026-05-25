from fastapi.testclient import TestClient

from edison_core.config import EdisonSettings
from edison_core.main import create_app


def test_job_routes_create_list_cancel_and_events(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        comfyui_base_url="",
    )
    client = TestClient(create_app(settings))

    created = client.post(
        "/api/v1/jobs",
        json={"job_type": "document", "title": "Draft report", "prompt": "Summarize the project"},
    )
    job_id = created.json()["id"]
    listed = client.get("/api/v1/jobs")
    cancelled = client.post(f"/api/v1/jobs/{job_id}/cancel")
    events = client.get(f"/api/v1/jobs/{job_id}/events")

    assert created.status_code == 201
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == job_id
    assert cancelled.json()["status"] == "cancelled"
    assert [event["status"] for event in events.json()] == ["queued", "cancelled"]


def test_media_status_and_job_report_setup_required_without_comfyui(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        comfyui_base_url="",
    )
    client = TestClient(create_app(settings))

    status = client.get("/api/v1/media/status")
    created = client.post(
        "/api/v1/media/jobs",
        json={"job_type": "image", "title": "Flux setup check", "prompt": "A neon Edison logo"},
    )
    events = client.get(f"/api/v1/jobs/{created.json()['id']}/events")

    assert status.status_code == 200
    assert status.json()["comfyui"]["status"] == "setup_required"
    assert status.json()["invokeai"]["status"] == "setup_required"
    assert status.json()["wan22"]["status"] == "setup_required"
    assert status.json()["modly"]["status"] == "setup_required"
    assert created.status_code == 201
    assert created.json()["status"] == "setup_required"
    assert events.json()[-1]["message"] == "ComfyUI base URL is not configured."


def test_media_jobs_route_to_wan22_and_modly_by_job_type(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        comfyui_base_url="",
        wan22_base_url="",
        modly_base_url="",
    )
    client = TestClient(create_app(settings))

    video_job = client.post(
        "/api/v1/media/jobs",
        json={"job_type": "video", "title": "Wan 2.2 generation", "prompt": "A city timelapse"},
    )
    mesh_job = client.post(
        "/api/v1/media/jobs",
        json={"job_type": "mesh", "title": "Modly generation", "prompt": "A stylized helmet"},
    )

    assert video_job.status_code == 201
    assert video_job.json()["backend"] == "wan22"
    assert video_job.json()["status"] == "setup_required"
    assert mesh_job.status_code == 201
    assert mesh_job.json()["backend"] == "modly"
    assert mesh_job.json()["status"] == "setup_required"


def test_media_job_can_target_invokeai_backend_explicitly(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        comfyui_base_url="",
        invokeai_base_url="",
    )
    client = TestClient(create_app(settings))

    created = client.post(
        "/api/v1/media/jobs",
        json={
            "job_type": "image",
            "title": "InvokeAI image",
            "prompt": "A sci-fi portrait",
            "backend": "invokeai",
        },
    )

    assert created.status_code == 201
    assert created.json()["backend"] == "invokeai"
    assert created.json()["status"] == "setup_required"
from fastapi.testclient import TestClient

from edison_core.config import EdisonSettings
from edison_core.main import create_app
from edison_core.schemas import ArtifactCreate, ArtifactKind, JobCreate, JobStatus, JobType


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


def test_media_modes_and_minecraft_generation_create_planning_artifact(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        artifact_root=tmp_path / "artifacts",
        comfyui_base_url="",
    )
    client = TestClient(create_app(settings))

    modes = client.get("/api/v1/media/modes")
    created = client.post(
        "/api/v1/media/generate",
        json={
            "mode": "minecraft_structure",
            "prompt": "A compact 1.7.10 redstone starter base with a hidden storage room",
        },
    )
    artifact = client.get(f"/api/v1/artifacts/{created.json()['result_artifact_id']}")

    assert modes.status_code == 200
    assert {
        "image",
        "minecraft_texture",
        "minecraft_model",
        "minecraft_world",
        "minecraft_structure",
        "minecraft_texture_pack",
        "product_render",
        "social_media_content",
    }.issubset({item["id"] for item in modes.json()})
    assert created.status_code == 201
    assert created.json()["status"] == "complete"
    assert created.json()["backend"] == "minecraft-suite"
    assert created.json()["metadata"]["generation_mode"] == "minecraft_structure"
    assert artifact.status_code == 200
    artifact_path = tmp_path / artifact.json()["path"]
    assert artifact_path.exists()
    assert "Minecraft 1.7.10" in artifact_path.read_text(encoding="utf-8")


def test_toybox_status_uses_registered_workstation_snapshot(tmp_path):
    snapshot_path = tmp_path / "integration-discovery.local.json"
    snapshot_path.write_text(
        """
        {
          "host": "main-pc",
          "checked_at": "2026-06-04T10:00:00Z",
          "tools": [
            {"name": "ollama", "detected": true, "path": "C:/Users/mike/AppData/Local/Programs/Ollama/ollama.exe"},
            {"name": "codex", "detected": true, "path": "C:/Program Files/WindowsApps/OpenAI.Codex/codex.exe"}
          ],
          "paths": [
            {"name": "Fusion 360", "path": "C:/Users/mike/AppData/Local/Autodesk/webdeploy/production/Fusion360.exe"},
            {"name": "Bambu Studio", "path": "C:/Program Files/Bambu Studio/bambu-studio.exe"},
            {"name": "OrcaSlicer", "path": "C:/Program Files/OrcaSlicer/orca-slicer.exe"},
            {"name": "Cura", "path": "C:/Program Files/UltiMaker Cura 5.11.0/CuraEngine.exe"},
            {"name": "Blockbench", "path": "C:/Users/mike/AppData/Local/Programs/Blockbench/Blockbench.exe"}
          ],
          "printers": [
            {
              "name": "Mike's shipping label printer",
              "driver": "DYMO LabelWriter 5XL",
              "port": "DYMO Label Writer 5XL on network",
              "status": "Normal"
            }
          ],
          "mcp_servers": ["edison-knowledge", "edison-workspace"]
        }
        """,
        encoding="utf-8",
    )
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        integration_discovery_path=snapshot_path,
        comfyui_base_url="",
    )
    client = TestClient(create_app(settings))

    integrations = client.get("/api/v1/capabilities/integrations")
    toybox = client.get("/api/v1/toybox/status")

    assert integrations.status_code == 200
    integration_ids = {item["id"]: item for item in integrations.json()["integrations"]}
    assert integration_ids["workstation-cad-tools"]["status"] == "ready"
    assert integration_ids["workstation-label-printer"]["status"] == "ready"
    assert integration_ids["workstation-mcp-config"]["status"] == "ready"
    assert toybox.status_code == 200
    printer_ids = {item["id"]: item for item in toybox.json()["printers"]}
    assert printer_ids["fusion360"]["status"] == "ready"
    assert printer_ids["dymo-5xl"]["status"] == "ready"
    assert {item["id"] for item in toybox.json()["notification_channels"]} == {"sms", "push", "email", "desktop"}


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


def test_completed_media_job_can_deliver_artifact_to_chat(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        artifact_root=tmp_path / "artifacts",
        comfyui_base_url="",
    )
    app = create_app(settings)
    client = TestClient(app)
    conversation = client.post(
        "/api/v1/conversations",
        json={"title": "Media delivery", "mode": "media", "memory_enabled": True},
    ).json()
    store = app.state.generation_store
    job = store.create_job(
        JobCreate(
            job_type=JobType.IMAGE,
            title="Chat image",
            prompt="A glass Edison logo",
            backend="comfyui",
            metadata={"conversation_id": conversation["id"], "deliver_to_chat": True},
        ),
        status=JobStatus.GENERATING,
    )
    artifact = store.create_artifact(
        ArtifactCreate(
            kind=ArtifactKind.IMAGE,
            title="Chat image #1",
            path="artifacts/comfyui/job/output.png",
            mime_type="image/png",
            source_job_id=job.id,
        )
    )
    store.finalize_job_result(job.id, artifact.id, JobStatus.COMPLETE, "Image complete")

    delivered = client.post(f"/api/v1/media/jobs/{job.id}/deliver", json={})
    loaded = client.get(f"/api/v1/conversations/{conversation['id']}").json()

    assert delivered.status_code == 201
    assert delivered.json()["metadata"]["artifacts"][0]["id"] == artifact.id
    assert loaded["messages"][0]["metadata"]["delivery_type"] == "media_result"

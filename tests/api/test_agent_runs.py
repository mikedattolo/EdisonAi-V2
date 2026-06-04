from pathlib import Path

from fastapi.testclient import TestClient

from edison_core.config import EdisonSettings
from edison_core.main import create_app


def test_agent_run_routes_create_update_and_list(tmp_path):
    client = TestClient(create_app(_settings(tmp_path)))

    created = client.post(
        "/api/v1/agents/runs",
        json={"prompt": "Check the Edison hardware and explain next steps.", "mode": "agent"},
    )
    run_id = created.json()["id"]
    updated = client.put(
        f"/api/v1/agents/runs/{run_id}/status",
        json={"status": "completed", "current_step": "Saved summary", "progress_percent": 100},
    )
    listed = client.get("/api/v1/agents/runs")

    assert created.status_code == 201
    assert created.json()["status"] == "planning"
    assert len(created.json()["events"]) >= 2
    assert updated.status_code == 200
    assert updated.json()["status"] == "completed"
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == run_id


def test_agent_chat_turn_creates_visible_agent_run(tmp_path):
    client = TestClient(create_app(_settings(tmp_path)))

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "Plan the next Edison hardware setup steps",
            "mode": "auto",
            "agent_enabled": True,
        },
    )
    runs = client.get("/api/v1/agents/runs")
    run_id = response.json()["assistant_message"]["metadata"]["agent_run_id"]
    loaded = client.get(f"/api/v1/agents/runs/{run_id}")

    assert response.status_code == 201
    assert run_id
    assert runs.status_code == 200
    assert runs.json()[0]["id"] == run_id
    assert loaded.json()["conversation_id"] == response.json()["conversation"]["id"]
    assert loaded.json()["status"] == "completed"
    assert any(event["title"] == "Context assembled" for event in loaded.json()["events"])


def _settings(tmp_path: Path) -> EdisonSettings:
    return EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        artifact_root=tmp_path / "artifacts",
        log_root=tmp_path / "logs",
        workspace_roots=[tmp_path],
    )

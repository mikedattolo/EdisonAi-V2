from fastapi.testclient import TestClient

from edison_core.config import EdisonSettings
from edison_core.main import create_app
from edison_core.schemas import GPUDevice, GPUFanControlUpdate
from edison_core.services import system_status
from edison_core.services.system_status import GPUFanControlService


def test_health_and_status_routes(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        artifact_root=tmp_path / "artifacts",
        log_root=tmp_path / "logs",
    )
    client = TestClient(create_app(settings))

    health = client.get("/health")
    status = client.get("/api/v1/status")

    assert health.status_code == 200
    assert health.json()["service"] == "edison-core-api"
    assert status.status_code == 200
    assert status.json()["model_count"] >= 1


def test_capability_registry_lists_mcp_servers_and_plugins(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        artifact_root=tmp_path / "artifacts",
        log_root=tmp_path / "logs",
        workspace_roots=[tmp_path],
    )
    client = TestClient(create_app(settings))

    response = client.get("/api/v1/capabilities")
    body = response.json()

    assert response.status_code == 200
    assert {server["id"] for server in body["mcp_servers"]} >= {"edison-knowledge", "edison-workspace"}
    assert {plugin["target"] for plugin in body["plugins"]} >= {"codex", "claude-code"}
    assert "mcp-agents" in body["knowledge_presets"]


def test_gpu_fan_control_routes_are_safe_by_default(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        artifact_root=tmp_path / "artifacts",
        log_root=tmp_path / "logs",
    )
    client = TestClient(create_app(settings))

    snapshot = client.get("/api/v1/system/fans")
    updated = client.put(
        "/api/v1/system/fans/0",
        json={"mode": "manual", "manual_speed_percent": 58},
    )

    assert snapshot.status_code == 200
    assert snapshot.json()["hardware_control_enabled"] is False
    assert updated.status_code == 200
    assert updated.json()["policy"]["mode"] == "manual"
    assert updated.json()["target_speed_percent"] == 58
    assert updated.json()["applied"] is False


def test_gpu_fan_control_uses_display_and_multi_fan_targets(monkeypatch, tmp_path):
    calls = []

    class FakeGPUManager:
        def detect_gpus(self):
            return [
                GPUDevice(index=0, name="RTX 5060 Ti"),
                GPUDevice(index=1, name="RTX 4060 Ti"),
                GPUDevice(index=2, name="RTX 3090"),
            ]

    class FakeResult:
        returncode = 0
        stderr = ""

        def __init__(self, stdout: str = "") -> None:
            self.stdout = stdout

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command == ["nvidia-settings", "-q", "fans"]:
            return FakeResult(
                "Attribute 'fans' (edison:99): 5.\n"
                "  [fan:0] [fan:1] [fan:2] [fan:3] [fan:4]\n"
            )
        return FakeResult()

    monkeypatch.setattr(system_status.subprocess, "run", fake_run)
    service = GPUFanControlService(
        EdisonSettings(
            database_path=tmp_path / "edison.sqlite3",
            model_registry_path=tmp_path / "missing-models.json",
            artifact_root=tmp_path / "artifacts",
            log_root=tmp_path / "logs",
            gpu_fan_control_enabled=True,
            gpu_fan_control_backend="nvidia-settings",
            gpu_fan_control_display=":99",
        ),
        FakeGPUManager(),
    )

    updated = service.update_policy(
        1,
        GPUFanControlUpdate(mode="manual", manual_speed_percent=58),
    )

    apply_command, apply_kwargs = calls[-1]
    assert updated.applied is True
    assert updated.target_fan_ids == [1, 2]
    assert apply_kwargs["env"]["DISPLAY"] == ":99"
    assert "[fan:1]/GPUTargetFanSpeed=58" in apply_command
    assert "[fan:2]/GPUTargetFanSpeed=58" in apply_command


def test_conversation_routes_round_trip(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
    )
    client = TestClient(create_app(settings))

    created = client.post(
        "/api/v1/conversations",
        json={"title": "Foundation", "mode": "chat", "memory_enabled": True},
    )
    conversation_id = created.json()["id"]
    message = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"role": "user", "content": "Keep this local-first."},
    )
    loaded = client.get(f"/api/v1/conversations/{conversation_id}")

    assert created.status_code == 201
    assert message.status_code == 201
    assert loaded.status_code == 200
    assert loaded.json()["messages"][0]["content"] == "Keep this local-first."


def test_chat_route_creates_conversation_and_assistant_message(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/v1/chat",
        json={"message": "Hello Edison", "mode": "chat", "memory_enabled": True},
    )

    body = response.json()
    messages = body["conversation"]["messages"]

    assert response.status_code == 201
    assert body["inference"]["finish_reason"] == "not_configured"
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["model"] == "local-general-chat"


def test_chat_auto_mode_routes_to_coding_with_workspace_context(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')\n", encoding="utf-8")
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        workspace_roots=[tmp_path],
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "Refactor this Python entrypoint",
            "mode": "auto",
            "workspace_path": "main.py",
            "memory_enabled": True,
        },
    )

    body = response.json()
    assistant_metadata = body["assistant_message"]["metadata"]

    assert response.status_code == 201
    assert body["model_selection"]["mode"] == "coding"
    assert assistant_metadata["requested_mode"] == "auto"
    assert assistant_metadata["resolved_mode"] == "coding"
    assert assistant_metadata["workspace_context"]["enabled"] is True


def test_chat_auto_mode_routes_to_agent_when_toggle_enabled(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        workspace_roots=[tmp_path],
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "Plan the next three Edison setup steps",
            "mode": "auto",
            "agent_enabled": True,
            "memory_enabled": True,
        },
    )

    body = response.json()
    assistant_metadata = body["assistant_message"]["metadata"]

    assert response.status_code == 201
    assert body["model_selection"]["mode"] == "agent"
    assert assistant_metadata["agent_enabled"] is True
    assert assistant_metadata["intent_router"]["reason"] == "agent toggle enabled"


def test_chat_stream_route_persists_streamed_turn(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
    )
    client = TestClient(create_app(settings))

    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"message": "Hello stream", "mode": "chat", "memory_enabled": True},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: start" in body
    assert "event: token" in body
    assert "event: done" in body

    conversations = client.get("/api/v1/conversations").json()
    loaded = client.get(f"/api/v1/conversations/{conversations[0]['id']}").json()
    assert [message["role"] for message in loaded["messages"]] == ["user", "assistant"]
    assert loaded["messages"][1]["metadata"]["streamed"] is True


def test_coding_chat_includes_workspace_context_metadata(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')\n", encoding="utf-8")
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        workspace_roots=[tmp_path],
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "Refactor this entrypoint",
            "mode": "coding",
            "workspace_path": "missing.py",
            "memory_enabled": True,
        },
    )

    body = response.json()
    assistant_metadata = body["assistant_message"]["metadata"]

    assert response.status_code == 201
    assert assistant_metadata["workspace_context"]["enabled"] is True
    assert assistant_metadata["workspace_context"]["mode"] == "coding"
    assert assistant_metadata["workspace_context"]["target_path"] == "missing.py"
    assert assistant_metadata["workspace_context"]["warnings"]


def test_coding_chat_focus_paths_are_included_in_workspace_context(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Edison\n", encoding="utf-8")
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        workspace_roots=[tmp_path],
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "Review these files",
            "mode": "coding",
            "workspace_path": "main.py",
            "workspace_context_paths": ["README.md", "main.py"],
            "memory_enabled": True,
        },
    )

    body = response.json()
    assistant_metadata = body["assistant_message"]["metadata"]

    assert response.status_code == 201
    assert assistant_metadata["workspace_context"]["focus_paths"] == ["main.py", "README.md"]


def test_workspace_projects_create_separate_code_space_root(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        workspace_roots=[tmp_path / "edison-app"],
        project_root=tmp_path / "projects",
    )
    settings.workspace_roots[0].mkdir()
    client = TestClient(create_app(settings))

    created = client.post(
        "/api/v1/workspace/projects",
        json={"name": "Robot Dashboard", "prompt": "Build a dashboard for robot telemetry."},
    )
    roots = client.get("/api/v1/workspace/roots")
    readme = client.get(
        "/api/v1/workspace/files/content",
        params={"root_id": created.json()["id"], "path": "README.md"},
    )

    assert created.status_code == 201
    assert created.json()["id"] == "robot-dashboard"
    assert created.json()["path"].endswith("robot-dashboard")
    assert roots.status_code == 200
    assert {root["id"] for root in roots.json()} == {"app", "robot-dashboard"}
    assert readme.status_code == 200
    assert "robot telemetry" in readme.json()["content"]


def test_chat_includes_knowledge_context_metadata(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        workspace_roots=[tmp_path],
    )
    client = TestClient(create_app(settings))

    ingested = client.post(
        "/api/v1/knowledge/ingest/text",
        json={
            "title": "Wiki: Machine Learning",
            "text": "Machine learning uses data-driven models and training datasets.",
        },
    )
    assert ingested.status_code == 201

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "What is machine learning?",
            "mode": "chat",
            "include_knowledge_context": True,
            "max_knowledge_context_matches": 3,
        },
    )

    body = response.json()
    assistant_metadata = body["assistant_message"]["metadata"]
    knowledge_context = assistant_metadata["knowledge_context"]

    assert response.status_code == 201
    assert knowledge_context["enabled"] is True
    assert knowledge_context["matches"]
    assert knowledge_context["matches"][0]["source_title"] == "Wiki: Machine Learning"
    assert knowledge_context["matches"][0]["snippet"]

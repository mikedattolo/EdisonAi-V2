from fastapi.testclient import TestClient

from edison_core.config import EdisonSettings
from edison_core.main import create_app


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

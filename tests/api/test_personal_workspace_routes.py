from fastapi.testclient import TestClient

from edison_core.config import EdisonSettings
from edison_core.main import create_app


def test_organizer_items_round_trip(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        workspace_roots=[tmp_path],
    )
    client = TestClient(create_app(settings))

    created = client.post(
        "/api/v1/organizer/items",
        json={
            "kind": "task",
            "title": "Wire Odysseus organizer",
            "body": "Persist tasks in Edison",
            "tags": ["odysseus"],
        },
    )
    item_id = created.json()["id"]
    updated = client.put(f"/api/v1/organizer/items/{item_id}", json={"status": "done"})
    listed = client.get("/api/v1/organizer/items?kind=task")

    assert created.status_code == 201
    assert updated.status_code == 200
    assert updated.json()["status"] == "done"
    assert listed.status_code == 200
    assert listed.json()[0]["title"] == "Wire Odysseus organizer"


def test_documents_ingest_and_search_compare(tmp_path):
    (tmp_path / "guide.md").write_text("Edison workspace search can find local files.", encoding="utf-8")
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        workspace_roots=[tmp_path],
    )
    client = TestClient(create_app(settings))

    document = client.post(
        "/api/v1/documents",
        json={
            "title": "Odysseus Notes",
            "content": "Deep research should compare knowledge, documents, and workspace code.",
            "tags": ["research"],
        },
    )
    document_id = document.json()["id"]
    ingested = client.post(f"/api/v1/documents/{document_id}/ingest")
    compared = client.post(
        "/api/v1/search/compare",
        json={
            "query": "deep research workspace",
            "providers": ["knowledge", "workspace", "documents"],
            "max_results": 3,
        },
    )

    assert document.status_code == 201
    assert ingested.status_code == 201
    assert ingested.json()["metadata"]["document_id"] == document_id
    assert compared.status_code == 200
    assert compared.json()["provider_counts"]["documents"] >= 1
    assert "knowledge" in compared.json()["results"]


def test_chat_can_include_personal_workspace_context(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        workspace_roots=[tmp_path],
    )
    client = TestClient(create_app(settings))

    client.post(
        "/api/v1/organizer/items",
        json={
            "kind": "task",
            "title": "Ship document workspace",
            "body": "Make personal context available to chat.",
        },
    )
    client.post(
        "/api/v1/documents",
        json={
            "title": "Personal Context Note",
            "content": "The chat pipeline should reference personal documents when requested.",
        },
    )
    response = client.post(
        "/api/v1/chat",
        json={
            "message": "What personal context exists for document workspace?",
            "mode": "chat",
            "include_personal_context": True,
            "max_personal_context_items": 6,
        },
    )

    assert response.status_code == 201
    metadata = response.json()["assistant_message"]["metadata"]["personal_context"]
    assert metadata["enabled"] is True
    assert metadata["items"][0]["title"] == "Ship document workspace"
    assert metadata["documents"][0]["title"] == "Personal Context Note"

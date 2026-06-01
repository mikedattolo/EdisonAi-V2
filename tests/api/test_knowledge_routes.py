from fastapi.testclient import TestClient

from edison_core.config import EdisonSettings
from edison_core.main import create_app


def test_knowledge_ingest_text_status_sources_and_search(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        workspace_roots=[tmp_path],
    )
    client = TestClient(create_app(settings))

    ingested = client.post(
        "/api/v1/knowledge/ingest/text",
        json={
            "title": "Python Basics",
            "text": "Python uses indentation. FastAPI builds APIs quickly.",
            "metadata": {"topic": "coding"},
        },
    )
    status = client.get("/api/v1/knowledge/status")
    sources = client.get("/api/v1/knowledge/sources")
    search = client.post(
        "/api/v1/knowledge/search",
        json={"query": "fastapi indentation", "max_results": 5},
    )

    assert ingested.status_code == 201
    assert status.status_code == 200
    assert status.json()["source_count"] == 1
    assert status.json()["chunk_count"] >= 1
    assert sources.status_code == 200
    assert sources.json()[0]["title"] == "Python Basics"
    assert search.status_code == 200
    assert search.json()[0]["source_title"] == "Python Basics"
    assert "snippet" in search.json()[0]


def test_knowledge_ingest_local_indexes_workspace_files(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("Edison uses local-first knowledge indexing.", encoding="utf-8")

    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        workspace_roots=[tmp_path],
    )
    client = TestClient(create_app(settings))

    ingested = client.post(
        "/api/v1/knowledge/ingest/local",
        json={"path": "docs", "glob": "**/*.md", "max_files": 20},
    )

    search = client.post(
        "/api/v1/knowledge/search",
        json={"query": "local-first knowledge", "max_results": 5},
    )

    assert ingested.status_code == 201
    assert len(ingested.json()) == 1
    assert search.status_code == 200
    assert search.json()[0]["source_kind"] == "local_file"
    assert search.json()[0]["path"] == "docs/guide.md"

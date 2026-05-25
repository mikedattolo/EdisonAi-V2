from fastapi.testclient import TestClient

from edison_core.config import EdisonSettings
from edison_core.main import create_app


def test_workspace_routes_expose_summary_files_content_and_search(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (tmp_path / "package.json").write_text('{"scripts":{"test":"echo ok"}}', encoding="utf-8")
    (src / "index.ts").write_text("export const label = 'Edison Copilot';\n", encoding="utf-8")
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        comfyui_base_url="",
        workspace_roots=[tmp_path],
    )
    client = TestClient(create_app(settings))

    summary = client.get("/api/v1/workspace/summary")
    files = client.get("/api/v1/workspace/files")
    content = client.get("/api/v1/workspace/files/content", params={"path": "src/index.ts"})
    search = client.post("/api/v1/workspace/search", json={"query": "Copilot"})
    scan = client.get("/api/v1/workspace/scan")

    assert summary.status_code == 200
    assert summary.json()["package_managers"] == ["Node"]
    assert files.status_code == 200
    assert files.json()[0]["name"] == "src"
    assert content.status_code == 200
    assert content.json()["language"] == "TypeScript"
    assert search.status_code == 200
    assert search.json()[0]["path"] == "src/index.ts"
    assert scan.status_code == 200
    assert any(command["command"] == "npm run test" for command in scan.json()["commands"])


def test_workspace_route_rejects_path_escape(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        comfyui_base_url="",
        workspace_roots=[tmp_path],
    )
    client = TestClient(create_app(settings))

    response = client.get("/api/v1/workspace/files/content", params={"path": "../secret.txt"})

    assert response.status_code == 403


def test_workspace_patch_routes_preview_apply_and_refuse_unapproved(tmp_path):
    (tmp_path / "README.md").write_text("old\n", encoding="utf-8")
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        comfyui_base_url="",
        workspace_roots=[tmp_path],
    )
    client = TestClient(create_app(settings))

    preview = client.post(
        "/api/v1/workspace/patches/preview",
        json={"path": "README.md", "proposed_content": "new\n"},
    )
    preview_events = client.get(f"/api/v1/jobs/{preview.json()['job']['id']}/events")
    unapproved = client.post(
        "/api/v1/workspace/patches/apply",
        json={"path": "README.md", "proposed_content": "new\n"},
    )
    applied = client.post(
        "/api/v1/workspace/patches/apply",
        json={
            "path": "README.md",
            "proposed_content": "new\n",
            "expected_sha256": preview.json()["current_sha256"],
            "approved": True,
        },
    )
    jobs = client.get("/api/v1/jobs", params={"job_type": "code"})

    assert preview.status_code == 200
    assert preview.json()["job"]["status"] == "complete"
    assert preview.json()["job"]["metadata"]["path"] == "README.md"
    assert "-old" in preview.json()["diff"]
    assert preview_events.status_code == 200
    assert [event["status"] for event in preview_events.json()] == ["queued", "generating", "complete"]
    assert unapproved.status_code == 403
    assert applied.status_code == 200
    assert applied.json()["job"]["status"] == "complete"
    assert applied.json()["job"]["metadata"]["path"] == "README.md"
    assert applied.json()["file"]["content"] == "new\n"
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "new\n"
    assert jobs.status_code == 200
    patch_jobs = [job for job in jobs.json() if job["backend"] == "workspace-patch"]
    assert len(patch_jobs) == 3
    assert any(job["title"].startswith("Preview patch README.md") and job["status"] == "complete" for job in patch_jobs)
    assert any(job["title"].startswith("Apply patch README.md") and job["status"] == "cancelled" for job in patch_jobs)
    completed_apply = next(
        job
        for job in patch_jobs
        if job["title"].startswith("Apply patch README.md") and job["status"] == "complete"
    )
    events = client.get(f"/api/v1/jobs/{completed_apply['id']}/events")
    assert events.status_code == 200
    assert [event["status"] for event in events.json()] == ["queued", "generating", "complete"]


def test_workspace_command_route_runs_detected_command_and_records_job(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    (tests_dir / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        comfyui_base_url="",
        workspace_roots=[tmp_path],
    )
    client = TestClient(create_app(settings))

    unapproved = client.post(
        "/api/v1/workspace/commands/run",
        json={"command": "python -m pytest", "cwd": ".", "timeout_seconds": 30},
    )
    result = client.post(
        "/api/v1/workspace/commands/run",
        json={"command": "python -m pytest", "cwd": ".", "timeout_seconds": 30, "approved": True},
    )
    events = client.get(f"/api/v1/jobs/{result.json()['job']['id']}/events")

    assert unapproved.status_code == 403
    assert result.status_code == 200
    assert result.json()["status"] == "complete"
    assert result.json()["job"]["status"] == "complete"
    assert result.json()["exit_code"] == 0
    assert "passed" in result.json()["stdout"]
    assert events.status_code == 200
    assert events.json()[-1]["metadata"]["exit_code"] == 0


def test_workspace_instruction_and_index_routes(tmp_path):
    src = tmp_path / "apps" / "api"
    src.mkdir(parents=True)
    (src / "main.py").write_text("print('hello')\n", encoding="utf-8")
    github_dir = tmp_path / ".github"
    (github_dir / "instructions").mkdir(parents=True)
    (github_dir / "prompts").mkdir(parents=True)
    (github_dir / "copilot-instructions.md").write_text("Repo rules\n", encoding="utf-8")
    (github_dir / "instructions" / "python.instructions.md").write_text(
        "---\napplyTo: \"apps/api/**\"\n---\nPython rules\n",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("Agent rules\n", encoding="utf-8")

    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        comfyui_base_url="",
        workspace_roots=[tmp_path],
    )
    client = TestClient(create_app(settings))

    instructions = client.get("/api/v1/workspace/instructions")
    context = client.get("/api/v1/workspace/instructions/context", params={"path": "apps/api/main.py"})
    initial_status = client.get("/api/v1/workspace/index/status")
    rebuilt_status = client.post("/api/v1/workspace/index/rebuild")
    search = client.post("/api/v1/workspace/index/search", json={"query": "python rules"})
    jobs = client.get("/api/v1/jobs", params={"job_type": "code"})

    assert instructions.status_code == 200
    assert any(item["path"] == ".github/copilot-instructions.md" for item in instructions.json())
    assert context.status_code == 200
    assert "Repo rules" in context.json()["combined_text"]
    assert initial_status.status_code == 200
    assert rebuilt_status.status_code == 200
    assert rebuilt_status.json()["indexed_file_count"] >= 1
    assert search.status_code == 200
    assert any(match["path"] == ".github/instructions/python.instructions.md" for match in search.json())
    index_jobs = [job for job in jobs.json() if job["backend"] == "workspace-index"]
    assert len(index_jobs) == 1
    assert index_jobs[0]["status"] == "complete"
from edison_core.schemas import (
    JobRecord,
    JobStatus,
    JobType,
    WorkspaceCommandRunRequest,
    WorkspaceIndexSearchRequest,
    WorkspacePatchApplyRequest,
    WorkspacePatchRequest,
    WorkspaceSearchRequest,
    utc_now,
)
from edison_core.services.workspace_tools import (
    WorkspaceAccessError,
    WorkspaceCommandApprovalError,
    WorkspaceCommandNotAllowedError,
    WorkspacePatchApprovalError,
    WorkspacePatchConflictError,
    WorkspaceTools,
)


def test_workspace_tools_summarize_list_read_and_search(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    (src / "app.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignored.js").write_text("FastAPI", encoding="utf-8")

    workspace = WorkspaceTools(tmp_path)

    summary = workspace.summarize()
    entries = workspace.list_directory()
    file_record = workspace.read_file("src/app.py")
    matches = workspace.search(WorkspaceSearchRequest(query="FastAPI"))

    assert summary.root_name == tmp_path.name
    assert summary.package_managers == ["Python"]
    assert summary.languages["Python"] == 1
    assert [entry.name for entry in entries] == ["src", "pyproject.toml"]
    assert file_record.language == "Python"
    assert "FastAPI" in file_record.content
    assert matches[0].path == "src/app.py"


def test_workspace_tools_scan_detects_entrypoints_commands_and_tests(tmp_path):
    app_dir = tmp_path / "apps" / "web"
    api_dir = tmp_path / "apps" / "api" / "edison_core"
    app_dir.mkdir(parents=True)
    api_dir.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    (app_dir / "package.json").write_text(
        '{"scripts":{"dev":"vite","build":"vite build","test":"vitest"}}',
        encoding="utf-8",
    )
    (app_dir / "vite.config.ts").write_text("export default {};\n", encoding="utf-8")
    (api_dir / "main.py").write_text("from fastapi import FastAPI\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()

    scan = WorkspaceTools(tmp_path).scan()

    assert "FastAPI" in scan.stacks
    assert "Vite" in scan.stacks
    assert any(entrypoint.kind == "FastAPI app" for entrypoint in scan.entrypoints)
    assert any(command.command == "npm run build" for command in scan.commands)
    assert any("python -m pytest" in target for target in scan.test_targets)


def test_workspace_tools_reject_path_escape(tmp_path):
    workspace = WorkspaceTools(tmp_path)

    try:
        workspace.read_file("../outside.txt")
    except WorkspaceAccessError as error:
        assert "outside" in str(error)
    else:
        raise AssertionError("expected workspace access error")


def test_workspace_tools_preview_and_apply_patch_with_approval(tmp_path):
    path = tmp_path / "src" / "app.py"
    path.parent.mkdir()
    path.write_text("print('old')\n", encoding="utf-8")
    workspace = WorkspaceTools(tmp_path)

    preview = workspace.preview_patch(WorkspacePatchRequest(path="src/app.py", proposed_content="print('new')\n"))
    result = workspace.apply_patch(
        WorkspacePatchApplyRequest(
            path="src/app.py",
            proposed_content="print('new')\n",
            expected_sha256=preview.current_sha256,
            approved=True,
        )
    )

    assert "-print('old')" in preview.diff
    assert "+print('new')" in preview.diff
    assert preview.additions == 1
    assert preview.deletions == 1
    assert result.applied is True
    assert path.read_text(encoding="utf-8") == "print('new')\n"


def test_workspace_tools_refuse_unapproved_and_stale_patch(tmp_path):
    path = tmp_path / "README.md"
    path.write_text("old\n", encoding="utf-8")
    workspace = WorkspaceTools(tmp_path)
    preview = workspace.preview_patch(WorkspacePatchRequest(path="README.md", proposed_content="new\n"))

    try:
        workspace.apply_patch(WorkspacePatchApplyRequest(path="README.md", proposed_content="new\n"))
    except WorkspacePatchApprovalError as error:
        assert "approval" in str(error).lower()
    else:
        raise AssertionError("expected approval error")

    path.write_text("changed elsewhere\n", encoding="utf-8")
    try:
        workspace.apply_patch(
            WorkspacePatchApplyRequest(
                path="README.md",
                proposed_content="new\n",
                expected_sha256=preview.current_sha256,
                approved=True,
            )
        )
    except WorkspacePatchConflictError as error:
        assert "changed" in str(error)
    else:
        raise AssertionError("expected patch conflict error")


def test_workspace_tools_run_detected_command_with_approval(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    (tests_dir / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    job = JobRecord(
        id="job_test",
        job_type=JobType.CODE,
        status=JobStatus.GENERATING,
        title="Run Python tests",
        backend="workspace-command",
        metadata={},
        created_at=utc_now(),
        updated_at=utc_now(),
    )

    result = WorkspaceTools(tmp_path).run_command(
        WorkspaceCommandRunRequest(command="python -m pytest", cwd=".", approved=True, timeout_seconds=30),
        job,
    )

    assert result.status == "complete"
    assert result.exit_code == 0
    assert "passed" in result.stdout


def test_workspace_tools_refuse_unapproved_and_unknown_commands(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    job = JobRecord(
        id="job_test",
        job_type=JobType.CODE,
        status=JobStatus.GENERATING,
        title="Run Python tests",
        backend="workspace-command",
        metadata={},
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    workspace = WorkspaceTools(tmp_path)

    try:
        workspace.run_command(WorkspaceCommandRunRequest(command="python -m pytest", cwd="."), job)
    except WorkspaceCommandApprovalError as error:
        assert "approval" in str(error).lower()
    else:
        raise AssertionError("expected approval error")

    try:
        workspace.run_command(WorkspaceCommandRunRequest(command="python -m pip freeze", cwd=".", approved=True), job)
    except WorkspaceCommandNotAllowedError as error:
        assert "detected" in str(error)
    else:
        raise AssertionError("expected command allowlist error")


def test_workspace_tools_instruction_files_and_context(tmp_path):
    src = tmp_path / "apps" / "api"
    src.mkdir(parents=True)
    target = src / "main.py"
    target.write_text("print('hello')\n", encoding="utf-8")

    github_dir = tmp_path / ".github"
    (github_dir / "instructions").mkdir(parents=True)
    (github_dir / "prompts").mkdir(parents=True)
    (github_dir / "copilot-instructions.md").write_text("Repo rules\n", encoding="utf-8")
    (github_dir / "instructions" / "python.instructions.md").write_text(
        "---\napplyTo: \"apps/api/**\"\n---\nPython rules\n",
        encoding="utf-8",
    )
    (github_dir / "prompts" / "review.prompt.md").write_text("/review-code\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("Global agent behavior\n", encoding="utf-8")

    workspace = WorkspaceTools(tmp_path)
    instruction_files = workspace.list_instruction_files()
    context = workspace.instruction_context("apps/api/main.py")

    assert any(item.path == ".github/copilot-instructions.md" for item in instruction_files)
    assert any(item.path.endswith("python.instructions.md") for item in instruction_files)
    assert any(item.path == "AGENTS.md" for item in instruction_files)
    assert any(item.path.endswith("review.prompt.md") for item in instruction_files)
    assert len(context.selected_files) == 3
    assert "Repo rules" in context.combined_text
    assert "Global agent behavior" in context.combined_text
    assert "Python rules" in context.combined_text


def test_workspace_tools_semantic_index_status_and_search(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("def greet():\n    return 'edison index'\n", encoding="utf-8")
    (src / "b.ts").write_text("export const runner = 'agent tool routing';\n", encoding="utf-8")

    workspace = WorkspaceTools(tmp_path)
    initial_status = workspace.index_status()
    rebuilt_status = workspace.rebuild_index()
    matches = workspace.search_index(WorkspaceIndexSearchRequest(query="agent routing"))

    assert initial_status.is_stale is True
    assert rebuilt_status.indexed_file_count == 2
    assert rebuilt_status.is_stale is False
    assert matches[0].path == "src/b.ts"
    assert matches[0].score > 0
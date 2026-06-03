from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from edison_core.config import EdisonSettings
from edison_core.schemas import WorkspaceProjectCreate, WorkspaceProjectRecord, WorkspaceRootRecord
from edison_core.services.workspace_tools import WorkspaceAccessError, WorkspaceTools


class WorkspaceProjectManager:
    def __init__(self, settings: EdisonSettings) -> None:
        self.settings = settings
        self.app_root = settings.workspace_roots[0].expanduser().resolve()
        self.project_root = settings.project_root.expanduser().resolve()
        self.project_root.mkdir(parents=True, exist_ok=True)

    def list_roots(self) -> list[WorkspaceRootRecord]:
        roots: list[WorkspaceRootRecord] = [
            WorkspaceRootRecord(
                id="app",
                name="Edison App",
                path=str(self.app_root),
                kind="app",
                description="Main Edison V2 application repository.",
            )
        ]
        roots.extend(self.list_projects())
        return roots

    def list_projects(self) -> list[WorkspaceProjectRecord]:
        projects: list[WorkspaceProjectRecord] = []
        if not self.project_root.exists():
            return projects
        for path in sorted(self.project_root.iterdir(), key=lambda item: item.name.lower()):
            if path.is_dir():
                stat = path.stat()
                projects.append(
                    WorkspaceProjectRecord(
                        id=path.name,
                        name=_display_name(path.name),
                        path=str(path),
                        description=_read_first_heading(path / "README.md"),
                        created_at=datetime.fromtimestamp(stat.st_ctime, timezone.utc),
                    )
                )
        return projects

    def create_project(self, payload: WorkspaceProjectCreate) -> WorkspaceProjectRecord:
        slug = _slugify(payload.name)
        path = _dedupe_path(self.project_root / slug)
        path.mkdir(parents=True, exist_ok=False)
        (path / "README.md").write_text(_readme(payload.name, payload.prompt), encoding="utf-8")
        (path / "AGENTS.md").write_text(_agents(payload.prompt), encoding="utf-8")
        (path / ".gitignore").write_text("node_modules/\n.venv/\ndist/\nbuild/\n.env\n", encoding="utf-8")
        if payload.initialize_git:
            subprocess.run(["git", "init"], cwd=path, capture_output=True, text=True, timeout=10, check=False)
        stat = path.stat()
        return WorkspaceProjectRecord(
            id=path.name,
            name=payload.name.strip(),
            path=str(path),
            description=payload.prompt.strip()[:240],
            created_at=datetime.fromtimestamp(stat.st_ctime, timezone.utc),
        )

    def workspace_for(self, root_id: str | None) -> WorkspaceTools:
        root = self.path_for(root_id)
        return WorkspaceTools(root)

    def path_for(self, root_id: str | None) -> Path:
        if not root_id or root_id == "app":
            return self.app_root
        slug = _slugify(root_id)
        candidate = (self.project_root / slug).resolve()
        try:
            candidate.relative_to(self.project_root)
        except ValueError as error:
            raise WorkspaceAccessError("Workspace root is outside the configured projects directory.") from error
        if not candidate.exists() or not candidate.is_dir():
            raise WorkspaceAccessError(f"Workspace project {root_id!r} was not found.")
        return candidate


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip("-._")
    return slug or "edison-project"


def _dedupe_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.name}-{index}")
        if not candidate.exists():
            return candidate
    raise WorkspaceAccessError("Could not allocate a unique project folder.")


def _display_name(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def _read_first_heading(path: Path) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        clean = line.strip()
        if clean.startswith("# "):
            return clean[2:].strip()
    return None


def _readme(name: str, prompt: str) -> str:
    return f"# {name.strip()}\n\n{prompt.strip()}\n\n## Next Steps\n\n- Define the first runnable feature.\n- Add the app scaffold Edison should build from.\n- Run tests or a local preview before publishing.\n"


def _agents(prompt: str) -> str:
    return f"# Project Instructions\n\nBuild this project from the user's brief:\n\n{prompt.strip()}\n\nKeep edits scoped to this project folder unless the user explicitly asks to connect it to Edison.\n"

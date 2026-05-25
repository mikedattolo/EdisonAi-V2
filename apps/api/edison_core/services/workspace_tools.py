from __future__ import annotations

import json
import os
import difflib
import hashlib
import fnmatch
from datetime import datetime, timezone
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from edison_core.schemas import (
    WorkspaceCommand,
    WorkspaceEntry,
    WorkspaceEntrypoint,
    WorkspaceFile,
    WorkspacePatchApplyRequest,
    WorkspacePatchApplyResult,
    WorkspacePatchPreview,
    WorkspacePatchRequest,
    WorkspaceScan,
    WorkspaceSearchMatch,
    WorkspaceSearchRequest,
    WorkspaceSummary,
    WorkspaceCommandRunRequest,
    WorkspaceCommandRunResult,
    WorkspaceInstructionContext,
    WorkspaceInstructionFile,
    WorkspaceIndexSearchMatch,
    WorkspaceIndexSearchRequest,
    WorkspaceIndexStatus,
)


EXCLUDED_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".vite",
    "__pycache__",
    "artifacts",
    "data",
    "dist",
    "logs",
    "node_modules",
    "venv",
}

LANGUAGE_BY_SUFFIX = {
    ".css": "CSS",
    ".html": "HTML",
    ".js": "JavaScript",
    ".json": "JSON",
    ".jsx": "React",
    ".md": "Markdown",
    ".py": "Python",
    ".sh": "Shell",
    ".sql": "SQL",
    ".toml": "TOML",
    ".ts": "TypeScript",
    ".tsx": "TypeScript React",
    ".yaml": "YAML",
    ".yml": "YAML",
}

PACKAGE_MARKERS = {
    "Dockerfile": "Docker",
    "docker-compose.yml": "Docker Compose",
    "package.json": "Node",
    "pnpm-lock.yaml": "pnpm",
    "pyproject.toml": "Python",
    "requirements.txt": "Python requirements",
    "vite.config.ts": "Vite",
    "yarn.lock": "Yarn",
}

KEY_FILE_CANDIDATES = [
    "README.md",
    "pyproject.toml",
    "apps/api/edison_core/main.py",
    "apps/web/src/App.tsx",
    "config/edison.example.toml",
]

CONFIG_FILE_NAMES = {
    ".env.example",
    ".gitignore",
    "Dockerfile",
    "docker-compose.yml",
    "eslint.config.js",
    "package.json",
    "pnpm-lock.yaml",
    "pyproject.toml",
    "requirements.txt",
    "tsconfig.json",
    "tsconfig.app.json",
    "vite.config.ts",
    "yarn.lock",
}


class WorkspaceToolError(Exception):
    pass


class WorkspaceAccessError(WorkspaceToolError):
    pass


class WorkspaceNotFoundError(WorkspaceToolError):
    pass


class WorkspaceUnsupportedFileError(WorkspaceToolError):
    pass


class WorkspacePatchApprovalError(WorkspaceToolError):
    pass


class WorkspacePatchConflictError(WorkspaceToolError):
    pass

class WorkspaceCommandApprovalError(WorkspaceToolError):
    pass

class WorkspaceCommandNotAllowedError(WorkspaceToolError):
    pass


class WorkspaceTools:
    def __init__(self, root: Path, max_file_preview_bytes: int = 200_000) -> None:
        self.root = root.expanduser().resolve()
        self.max_file_preview_bytes = max_file_preview_bytes
        self._index_entries: list[dict[str, Any]] = []
        self._index_built_at: datetime | None = None
        self._index_latest_workspace_mtime: datetime | None = None

    def summarize(self) -> WorkspaceSummary:
        file_count = 0
        directory_count = 0
        languages: dict[str, int] = {}

        for current_root, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [name for name in dirnames if name not in EXCLUDED_NAMES]
            directory_count += len(dirnames)
            for filename in filenames:
                if filename in EXCLUDED_NAMES:
                    continue
                file_count += 1
                language = self._language_for(Path(filename))
                if language:
                    languages[language] = languages.get(language, 0) + 1

        package_managers = [label for marker, label in PACKAGE_MARKERS.items() if (self.root / marker).exists()]
        key_files = [path for path in KEY_FILE_CANDIDATES if (self.root / path).exists()]

        return WorkspaceSummary(
            root_name=self.root.name,
            root_path=str(self.root),
            file_count=file_count,
            directory_count=directory_count,
            languages=dict(sorted(languages.items(), key=lambda item: (-item[1], item[0]))),
            package_managers=package_managers,
            key_files=key_files,
        )

    def scan(self) -> WorkspaceScan:
        summary = self.summarize()
        commands = self._detect_commands()
        entrypoints = self._detect_entrypoints()
        config_files = self._detect_config_files()
        test_targets = self._detect_test_targets(commands)

        return WorkspaceScan(
            root_name=self.root.name,
            root_path=str(self.root),
            stacks=self._detect_stacks(summary.languages, summary.package_managers, entrypoints),
            package_managers=summary.package_managers,
            entrypoints=entrypoints,
            commands=commands,
            test_targets=test_targets,
            config_files=config_files,
            next_steps=self._next_steps(commands, test_targets),
        )

    def list_directory(self, relative_path: str = "", limit: int = 200) -> list[WorkspaceEntry]:
        path = self._resolve(relative_path)
        if not path.exists() or not path.is_dir():
            raise WorkspaceNotFoundError(f"Directory not found: {relative_path or '.'}")

        entries = [self._entry_for(child) for child in path.iterdir() if child.name not in EXCLUDED_NAMES]
        entries.sort(key=lambda entry: (entry.kind != "directory", entry.name.lower()))
        return entries[:limit]

    def read_file(self, relative_path: str) -> WorkspaceFile:
        path = self._resolve(relative_path)
        if not path.exists() or not path.is_file():
            raise WorkspaceNotFoundError(f"File not found: {relative_path}")

        stat = path.stat()
        raw = path.read_bytes()[: self.max_file_preview_bytes]
        if b"\x00" in raw:
            raise WorkspaceUnsupportedFileError("Binary file preview is not available")

        return WorkspaceFile(
            path=self._relative(path),
            name=path.name,
            size_bytes=stat.st_size,
            modified_at=self._modified_at(stat.st_mtime),
            language=self._language_for(path),
            content=raw.decode("utf-8", errors="replace"),
            truncated=stat.st_size > self.max_file_preview_bytes,
        )

    def search(self, request: WorkspaceSearchRequest) -> list[WorkspaceSearchMatch]:
        query = request.query if request.case_sensitive else request.query.lower()
        matches: list[WorkspaceSearchMatch] = []

        for path in self._iter_files():
            relative = self._relative(path)
            comparable_path = relative if request.case_sensitive else relative.lower()
            language = self._language_for(path)

            if query in comparable_path:
                matches.append(
                    WorkspaceSearchMatch(
                        path=relative,
                        name=path.name,
                        kind="file",
                        language=language,
                    )
                )
                if len(matches) >= request.max_results:
                    return matches

            if not request.include_content or self._looks_binary(path):
                continue

            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue

            for line_number, line in enumerate(lines, start=1):
                comparable_line = line if request.case_sensitive else line.lower()
                if query in comparable_line:
                    matches.append(
                        WorkspaceSearchMatch(
                            path=relative,
                            name=path.name,
                            kind="content",
                            line_number=line_number,
                            line_text=line.strip()[:240],
                            language=language,
                        )
                    )
                    if len(matches) >= request.max_results:
                        return matches

        return matches

    def preview_patch(self, request: WorkspacePatchRequest) -> WorkspacePatchPreview:
        path = self._resolve_writable(request.path)
        exists = path.exists()
        if exists and not path.is_file():
            raise WorkspaceUnsupportedFileError("Patch target is not a file")
        if not exists and not request.create_if_missing:
            raise WorkspaceNotFoundError(f"File not found: {request.path}")

        current_content = self._read_text_for_patch(path) if exists else ""
        current_hash = self._sha256(current_content) if exists else None
        if request.expected_sha256 and current_hash != request.expected_sha256:
            raise WorkspacePatchConflictError("File changed since the patch was previewed")

        diff = self._unified_diff(
            current_content,
            request.proposed_content,
            old_name=f"a/{self._relative(path)}" if exists else "/dev/null",
            new_name=f"b/{self._relative(path)}",
        )
        additions, deletions = self._diff_stats(diff)

        return WorkspacePatchPreview(
            path=self._relative(path),
            exists=exists,
            language=self._language_for(path),
            current_sha256=current_hash,
            proposed_sha256=self._sha256(request.proposed_content),
            diff=diff,
            additions=additions,
            deletions=deletions,
            risk_flags=self._patch_risk_flags(path, exists, additions, deletions),
        )

    def apply_patch(self, request: WorkspacePatchApplyRequest) -> WorkspacePatchApplyResult:
        if not request.approved:
            raise WorkspacePatchApprovalError("Patch approval is required before writing files")

        preview = self.preview_patch(request)
        path = self._resolve_writable(preview.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(request.proposed_content, encoding="utf-8")
        file_record = self.read_file(preview.path)

        return WorkspacePatchApplyResult(
            path=preview.path,
            applied=True,
            message="Patch applied",
            preview=preview,
            file=file_record,
        )

    def run_command(self, request: WorkspaceCommandRunRequest, job) -> WorkspaceCommandRunResult:
        if not request.approved:
            raise WorkspaceCommandApprovalError("Command approval is required before execution")

        command = request.command.strip()
        cwd = request.cwd.strip() or "."
        cwd_path = self._resolve(cwd if cwd != "." else "")
        if not cwd_path.exists() or not cwd_path.is_dir():
            raise WorkspaceNotFoundError(f"Command working directory not found: {cwd}")
        if not self._is_detected_command(command, cwd):
            raise WorkspaceCommandNotAllowedError("Command is not part of the detected workspace command set")

        started = time.monotonic()
        try:
            completed = subprocess.run(
                shlex.split(command),
                cwd=cwd_path,
                capture_output=True,
                check=False,
                text=True,
                timeout=request.timeout_seconds,
            )
            duration_ms = int((time.monotonic() - started) * 1000)
            stdout, stdout_truncated = self._truncate_output(completed.stdout)
            stderr, stderr_truncated = self._truncate_output(completed.stderr)
            return WorkspaceCommandRunResult(
                job=job,
                command=command,
                cwd=cwd,
                exit_code=completed.returncode,
                status="complete" if completed.returncode == 0 else "error",
                duration_ms=duration_ms,
                stdout=stdout,
                stderr=stderr,
                output_truncated=stdout_truncated or stderr_truncated,
            )
        except subprocess.TimeoutExpired as error:
            duration_ms = int((time.monotonic() - started) * 1000)
            stdout, stdout_truncated = self._truncate_output(error.stdout or "")
            stderr, stderr_truncated = self._truncate_output(error.stderr or "")
            return WorkspaceCommandRunResult(
                job=job,
                command=command,
                cwd=cwd,
                exit_code=None,
                status="timeout",
                duration_ms=duration_ms,
                stdout=stdout,
                stderr=stderr,
                output_truncated=stdout_truncated or stderr_truncated,
            )

    def list_instruction_files(self, limit: int = 200) -> list[WorkspaceInstructionFile]:
        instruction_files: list[WorkspaceInstructionFile] = []

        repo_file = self.root / ".github" / "copilot-instructions.md"
        if repo_file.exists() and repo_file.is_file():
            instruction_files.append(self._instruction_file_record(repo_file, "repository", None))

        for instruction_path in sorted((self.root / ".github" / "instructions").glob("**/*.instructions.md")):
            if instruction_path.is_file():
                instruction_files.append(
                    self._instruction_file_record(
                        instruction_path,
                        "path",
                        self._extract_apply_to(instruction_path),
                    )
                )

        for agent_path in self._find_named_files("AGENTS.md"):
            instruction_files.append(self._instruction_file_record(agent_path, "agent", None))

        for prompt_path in sorted((self.root / ".github" / "prompts").glob("**/*.prompt.md")):
            if prompt_path.is_file():
                instruction_files.append(self._instruction_file_record(prompt_path, "prompt", None))

        instruction_files.sort(key=lambda item: item.path)
        return instruction_files[:limit]

    def instruction_context(self, target_path: str) -> WorkspaceInstructionContext:
        resolved_target = self._resolve(target_path)
        if not resolved_target.exists() or not resolved_target.is_file():
            raise WorkspaceNotFoundError(f"File not found: {target_path}")

        relative_target = self._relative(resolved_target)
        selected: list[WorkspaceInstructionFile] = []
        warnings: list[str] = []
        sections: list[str] = []

        repo_file = self.root / ".github" / "copilot-instructions.md"
        if repo_file.exists() and repo_file.is_file():
            selected.append(self._instruction_file_record(repo_file, "repository", None))
            sections.append(self._instruction_section(repo_file, "repository"))

        nearest_agent = self._nearest_agents_file(resolved_target.parent)
        if nearest_agent is not None:
            selected.append(self._instruction_file_record(nearest_agent, "agent", None))
            sections.append(self._instruction_section(nearest_agent, "agent"))

        for instruction_path in sorted((self.root / ".github" / "instructions").glob("**/*.instructions.md")):
            if not instruction_path.is_file():
                continue
            apply_to = self._extract_apply_to(instruction_path)
            if apply_to and not self._matches_apply_to(relative_target, apply_to):
                continue
            if not apply_to:
                warnings.append(
                    f"{self._relative(instruction_path)} has no applyTo field; applied to all paths."
                )
            selected.append(self._instruction_file_record(instruction_path, "path", apply_to))
            sections.append(self._instruction_section(instruction_path, "path"))

        return WorkspaceInstructionContext(
            target_path=relative_target,
            selected_files=selected,
            combined_text="\n\n".join(section for section in sections if section).strip(),
            warnings=warnings,
        )

    def rebuild_index(self) -> WorkspaceIndexStatus:
        entries: list[dict[str, Any]] = []
        latest_mtime: float = 0.0

        for path in self._iter_files():
            if self._looks_binary(path):
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if not content.strip():
                continue
            stat = path.stat()
            latest_mtime = max(latest_mtime, stat.st_mtime)
            lines = content.splitlines()
            entries.append(
                {
                    "path": self._relative(path),
                    "language": self._language_for(path),
                    "content": content,
                    "content_lower": content.lower(),
                    "lines": lines,
                }
            )

        self._index_entries = entries
        self._index_built_at = datetime.now(timezone.utc)
        self._index_latest_workspace_mtime = (
            datetime.fromtimestamp(latest_mtime, timezone.utc) if latest_mtime > 0 else None
        )
        return self.index_status()

    def index_status(self) -> WorkspaceIndexStatus:
        latest_workspace_mtime = self._latest_workspace_mtime()
        is_stale = False
        if self._index_built_at is None:
            is_stale = True
        elif latest_workspace_mtime and self._index_latest_workspace_mtime:
            is_stale = latest_workspace_mtime > self._index_latest_workspace_mtime
        elif latest_workspace_mtime and self._index_latest_workspace_mtime is None:
            is_stale = True

        return WorkspaceIndexStatus(
            indexed_file_count=len(self._index_entries),
            index_built_at=self._index_built_at,
            latest_workspace_mtime=latest_workspace_mtime,
            is_stale=is_stale,
            excluded_paths=sorted(EXCLUDED_NAMES),
        )

    def search_index(self, request: WorkspaceIndexSearchRequest) -> list[WorkspaceIndexSearchMatch]:
        if self._index_built_at is None or not self._index_entries:
            self.rebuild_index()

        query_terms = [term for term in request.query.lower().split() if term]
        if not query_terms:
            return []

        scored: list[WorkspaceIndexSearchMatch] = []
        for entry in self._index_entries:
            score, snippet, line_number = self._score_index_entry(entry, query_terms)
            if score <= 0:
                continue
            scored.append(
                WorkspaceIndexSearchMatch(
                    path=entry["path"],
                    language=entry.get("language"),
                    score=round(score, 4),
                    snippet=snippet,
                    line_number=line_number,
                )
            )

        scored.sort(key=lambda item: (-item.score, item.path))
        return scored[: request.max_results]

    def _resolve(self, relative_path: str) -> Path:
        clean_path = relative_path.strip().lstrip("/") if relative_path else ""
        path = (self.root / clean_path).resolve()
        if not path.is_relative_to(self.root):
            raise WorkspaceAccessError("Path is outside the configured workspace root")
        return path

    def _resolve_writable(self, relative_path: str) -> Path:
        path = self._resolve(relative_path)
        relative_parts = path.relative_to(self.root).parts
        if any(part in EXCLUDED_NAMES for part in relative_parts):
            raise WorkspaceAccessError("Patch target is inside an excluded workspace path")
        return path

    def _relative(self, path: Path) -> str:
        relative = path.resolve().relative_to(self.root)
        return relative.as_posix()

    def _entry_for(self, path: Path) -> WorkspaceEntry:
        stat = path.stat()
        return WorkspaceEntry(
            path=self._relative(path),
            name=path.name,
            kind="directory" if path.is_dir() else "file",
            size_bytes=None if path.is_dir() else stat.st_size,
            modified_at=self._modified_at(stat.st_mtime),
            language=None if path.is_dir() else self._language_for(path),
        )

    def _iter_files(self):
        for current_root, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [name for name in dirnames if name not in EXCLUDED_NAMES]
            for filename in filenames:
                if filename in EXCLUDED_NAMES:
                    continue
                path = Path(current_root) / filename
                if path.is_file():
                    yield path

    def _detect_commands(self) -> list[WorkspaceCommand]:
        commands: list[WorkspaceCommand] = []

        pyproject = self.root / "pyproject.toml"
        if pyproject.exists():
            commands.append(
                WorkspaceCommand(
                    name="Install Python package",
                    command='python -m pip install -e ".[dev]"',
                    cwd=".",
                    category="install",
                    source="pyproject.toml",
                )
            )
            commands.append(
                WorkspaceCommand(
                    name="Run Python tests",
                    command="python -m pytest",
                    cwd=".",
                    category="test",
                    source="pyproject.toml",
                )
            )

        for package_json in self._find_named_files("package.json"):
            package_data = self._read_json(package_json)
            scripts = package_data.get("scripts", {}) if isinstance(package_data, dict) else {}
            if not isinstance(scripts, dict):
                continue
            cwd = self._relative(package_json.parent) or "."
            package_manager = self._node_package_manager(package_json.parent)
            for script_name in sorted(scripts):
                commands.append(
                    WorkspaceCommand(
                        name=f"{package_manager} {script_name}",
                        command=f"{package_manager} run {script_name}",
                        cwd=cwd,
                        category=self._script_category(script_name),
                        source=self._relative(package_json),
                    )
                )

        return commands

    def _detect_entrypoints(self) -> list[WorkspaceEntrypoint]:
        candidates = [
            ("apps/api/edison_core/main.py", "FastAPI app", "Python", "Core API application factory"),
            ("apps/web/src/App.tsx", "React app", "TypeScript React", "Main workbench UI"),
            ("apps/web/src/main.tsx", "React bootstrap", "TypeScript React", "Frontend mount point"),
            ("apps/web/vite.config.ts", "Vite config", "TypeScript", "Frontend dev server and proxy config"),
            ("pyproject.toml", "Python package", "TOML", "Backend package and test configuration"),
        ]
        entrypoints = [
            WorkspaceEntrypoint(path=path, kind=kind, language=language, description=description)
            for path, kind, language, description in candidates
            if (self.root / path).exists()
        ]
        for package_json in self._find_named_files("package.json"):
            relative = self._relative(package_json)
            if relative not in {entrypoint.path for entrypoint in entrypoints}:
                entrypoints.append(
                    WorkspaceEntrypoint(
                        path=relative,
                        kind="Node package",
                        language="JSON",
                        description="Package scripts and frontend tooling",
                    )
                )
        return entrypoints

    def _detect_config_files(self) -> list[str]:
        paths = [self._relative(path) for path in self._iter_files() if path.name in CONFIG_FILE_NAMES]
        paths.extend(self._relative(path) for path in self._iter_files() if "/config/" in f"/{self._relative(path)}")
        return sorted(set(paths))[:60]

    def _detect_test_targets(self, commands: list[WorkspaceCommand]) -> list[str]:
        targets = [f"{command.cwd}: {command.command}" for command in commands if command.category == "test"]
        if (self.root / "tests").exists() and not any("pytest" in target for target in targets):
            targets.append(".: python -m pytest")
        return targets

    def _detect_stacks(
        self,
        languages: dict[str, int],
        package_managers: list[str],
        entrypoints: list[WorkspaceEntrypoint],
    ) -> list[str]:
        stacks: list[str] = []
        if "Python" in languages or "Python" in package_managers:
            stacks.append("Python")
        if any(entrypoint.kind == "FastAPI app" for entrypoint in entrypoints):
            stacks.append("FastAPI")
        if any(entrypoint.kind in {"React app", "React bootstrap"} for entrypoint in entrypoints):
            stacks.append("React")
        if "TypeScript" in languages or "TypeScript React" in languages:
            stacks.append("TypeScript")
        if any(entrypoint.kind == "Vite config" for entrypoint in entrypoints):
            stacks.append("Vite")
        if "Node" in package_managers:
            stacks.append("Node")
        return list(dict.fromkeys(stacks))

    def _next_steps(self, commands: list[WorkspaceCommand], test_targets: list[str]) -> list[str]:
        steps = []
        if commands:
            steps.append("Persist command run presets and favorite validation workflows.")
        if test_targets:
            steps.append("Attach command validation results to coding-mode chat context.")
        steps.append("Persist patch proposals and approval events in job history.")
        steps.append("Continuously rebuild semantic workspace index for coding and review agents.")
        steps.append("Apply repository and path-specific instruction context to coding-mode chat turns.")
        return steps

    def _find_named_files(self, filename: str) -> list[Path]:
        return sorted((path for path in self._iter_files() if path.name == filename), key=lambda path: self._relative(path))

    def _read_json(self, path: Path) -> dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _node_package_manager(self, package_root: Path) -> str:
        if (package_root / "pnpm-lock.yaml").exists():
            return "pnpm"
        if (package_root / "yarn.lock").exists():
            return "yarn"
        return "npm"

    def _instruction_file_record(
        self,
        path: Path,
        instruction_type: str,
        apply_to: str | None,
    ) -> WorkspaceInstructionFile:
        stat = path.stat()
        return WorkspaceInstructionFile(
            path=self._relative(path),
            name=path.name,
            instruction_type=instruction_type,
            apply_to=apply_to,
            size_bytes=stat.st_size,
            modified_at=self._modified_at(stat.st_mtime),
        )

    def _instruction_section(self, path: Path, instruction_type: str) -> str:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return f"[{instruction_type}] {self._relative(path)}\n{content.strip()}"

    def _extract_apply_to(self, path: Path) -> str | None:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

        if not text.startswith("---"):
            return None

        lines = text.splitlines()
        end_index = None
        for i in range(1, min(len(lines), 80)):
            if lines[i].strip() == "---":
                end_index = i
                break
        if end_index is None:
            return None

        for line in lines[1:end_index]:
            stripped = line.strip()
            if stripped.startswith("applyTo:"):
                return stripped.split(":", 1)[1].strip().strip('"').strip("'") or None
        return None

    def _nearest_agents_file(self, start_dir: Path) -> Path | None:
        current = start_dir
        while current.is_relative_to(self.root):
            candidate = current / "AGENTS.md"
            if candidate.exists() and candidate.is_file():
                return candidate
            if current == self.root:
                break
            current = current.parent
        return None

    def _matches_apply_to(self, relative_path: str, apply_to: str) -> bool:
        patterns = [part.strip() for part in apply_to.replace(",", "\n").splitlines() if part.strip()]
        if not patterns:
            return True
        return any(fnmatch.fnmatch(relative_path, pattern) for pattern in patterns)

    def _latest_workspace_mtime(self) -> datetime | None:
        latest_mtime: float = 0.0
        for path in self._iter_files():
            try:
                latest_mtime = max(latest_mtime, path.stat().st_mtime)
            except OSError:
                continue
        if latest_mtime <= 0:
            return None
        return datetime.fromtimestamp(latest_mtime, timezone.utc)

    def _score_index_entry(
        self,
        entry: dict[str, Any],
        query_terms: list[str],
    ) -> tuple[float, str, int | None]:
        content_lower = entry["content_lower"]
        hits = sum(1 for term in query_terms if term in content_lower)
        if hits == 0:
            return 0.0, "", None

        first_line_number = None
        snippet = ""
        for i, line in enumerate(entry["lines"], start=1):
            lower_line = line.lower()
            if any(term in lower_line for term in query_terms):
                first_line_number = i
                snippet = line.strip()[:240]
                break

        length_penalty = max(len(entry["content"]) / 80_000, 1.0)
        score = (hits / len(query_terms)) / length_penalty
        return score, snippet or entry["path"], first_line_number

    def _script_category(self, script_name: str) -> str:
        normalized = script_name.lower()
        if normalized in {"dev", "start"}:
            return "dev"
        if "build" in normalized:
            return "build"
        if "test" in normalized:
            return "test"
        if "lint" in normalized:
            return "lint"
        if "type" in normalized or "check" in normalized:
            return "typecheck"
        if "format" in normalized:
            return "format"
        return "run"

    def _is_detected_command(self, command: str, cwd: str) -> bool:
        normalized_cwd = cwd.strip() or "."
        return any(candidate.command == command and candidate.cwd == normalized_cwd for candidate in self.scan().commands)

    def _truncate_output(self, output: str, limit: int = 20_000) -> tuple[str, bool]:
        if len(output) <= limit:
            return output, False
        return output[-limit:], True

    def _read_text_for_patch(self, path: Path) -> str:
        raw = path.read_bytes()
        if b"\x00" in raw:
            raise WorkspaceUnsupportedFileError("Binary file patching is not available")
        return raw.decode("utf-8", errors="replace")

    def _sha256(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _unified_diff(self, current: str, proposed: str, old_name: str, new_name: str) -> str:
        current_lines = current.splitlines()
        proposed_lines = proposed.splitlines()
        diff = difflib.unified_diff(current_lines, proposed_lines, fromfile=old_name, tofile=new_name, lineterm="")
        lines = list(diff)
        return "\n".join(lines) + ("\n" if lines else "")

    def _diff_stats(self, diff: str) -> tuple[int, int]:
        additions = 0
        deletions = 0
        for line in diff.splitlines():
            if line.startswith("+++") or line.startswith("---"):
                continue
            if line.startswith("+"):
                additions += 1
            elif line.startswith("-"):
                deletions += 1
        return additions, deletions

    def _patch_risk_flags(self, path: Path, exists: bool, additions: int, deletions: int) -> list[str]:
        flags: list[str] = []
        relative = self._relative(path)
        if not exists:
            flags.append("creates_new_file")
        if additions + deletions > 200:
            flags.append("large_change")
        if path.name in CONFIG_FILE_NAMES or relative.startswith("config/"):
            flags.append("configuration_change")
        if path.suffix.lower() in {".env", ".pem", ".key", ".crt"} or "secret" in path.name.lower():
            flags.append("sensitive_file")
        if path.suffix.lower() not in LANGUAGE_BY_SUFFIX and path.name != "Dockerfile":
            flags.append("unknown_file_type")
        return flags

    def _language_for(self, path: Path) -> str | None:
        if path.name == "Dockerfile":
            return "Dockerfile"
        return LANGUAGE_BY_SUFFIX.get(path.suffix.lower())

    def _looks_binary(self, path: Path) -> bool:
        try:
            sample = path.read_bytes()[:1024]
        except OSError:
            return True
        return b"\x00" in sample or path.stat().st_size > self.max_file_preview_bytes

    def _modified_at(self, timestamp: float) -> datetime:
        return datetime.fromtimestamp(timestamp, timezone.utc)
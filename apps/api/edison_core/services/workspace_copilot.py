from __future__ import annotations

import json
import re
from typing import Any, Literal

from edison_core.schemas import (
    ChatMode,
    InferenceRequest,
    JobRecord,
    JobStatus,
    WorkspaceCommandRunRequest,
    WorkspaceCopilotChange,
    WorkspaceCopilotTaskRequest,
    WorkspaceCopilotTaskResult,
    WorkspaceIndexSearchRequest,
    WorkspacePatchApplyRequest,
    WorkspacePatchRequest,
)
from edison_core.services.generation_store import GenerationStore
from edison_core.services.model_gateway import ModelGateway
from edison_core.services.workspace_tools import (
    WorkspaceAccessError,
    WorkspaceCommandNotAllowedError,
    WorkspaceNotFoundError,
    WorkspacePatchConflictError,
    WorkspaceTools,
    WorkspaceUnsupportedFileError,
)


class WorkspaceCopilot:
    def __init__(self, workspace: WorkspaceTools, gateway: ModelGateway, store: GenerationStore) -> None:
        self.workspace = workspace
        self.gateway = gateway
        self.store = store

    def run(self, request: WorkspaceCopilotTaskRequest, job: JobRecord) -> WorkspaceCopilotTaskResult:
        self.store.update_job_status(job.id, JobStatus.GENERATING, "Code Space Copilot task started", {})
        context = self._workspace_context(request)
        selection, inference = self.gateway.complete(
            InferenceRequest(
                mode=ChatMode.CODING,
                preferred_model=request.preferred_model,
                prompt=self._prompt(request, context),
                metadata={
                    "source": "workspace-copilot",
                    "root": str(self.workspace.root),
                    "response_format": {"type": "json_object"},
                    "timeout_seconds": 240,
                },
            )
        )

        plan = _parse_plan(inference.content)
        if not plan.get("changes"):
            plan = _fallback_plan(request, inference.content, inference.finish_reason)

        changes = self._apply_changes(plan, request)
        command_results = self._run_commands(plan, request, job)
        final_status = _result_status(inference.finish_reason, changes)
        final_job_status = JobStatus.COMPLETE if final_status in {"complete", "setup_required"} else JobStatus.ERROR
        final_job = self.store.update_job_status(
            job.id,
            final_job_status,
            "Code Space Copilot task completed",
            {
                "model_id": inference.model_id,
                "finish_reason": inference.finish_reason,
                "change_count": len(changes),
                "applied_change_count": len([change for change in changes if change.applied]),
                "command_count": len(command_results),
            },
        )
        return WorkspaceCopilotTaskResult(
            job=final_job,
            status=final_status,
            instruction=request.instruction,
            model_id=selection.model.id,
            summary=str(plan.get("summary") or _default_summary(inference.finish_reason)),
            changes=changes,
            commands=command_results,
            followups=[str(item) for item in plan.get("followups", []) if str(item).strip()][:6],
            raw_response=inference.content[:8000],
        )

    def _workspace_context(self, request: WorkspaceCopilotTaskRequest) -> dict[str, Any]:
        summary = self.workspace.summarize()
        scan = self.workspace.scan()
        indexed = self.workspace.search_index(
            WorkspaceIndexSearchRequest(query=request.instruction, max_results=request.max_context_files)
        )
        files: list[dict[str, Any]] = []
        target_paths = [path for path in request.target_paths if path.strip()]
        target_paths.extend(match.path for match in indexed)
        seen: set[str] = set()
        for path in target_paths:
            if path in seen:
                continue
            seen.add(path)
            try:
                file_record = self.workspace.read_file(path)
            except (WorkspaceAccessError, WorkspaceNotFoundError, WorkspaceUnsupportedFileError):
                continue
            files.append(
                {
                    "path": file_record.path,
                    "language": file_record.language,
                    "truncated": file_record.truncated,
                    "content": file_record.content[:12000],
                }
            )
            if len(files) >= request.max_context_files:
                break
        return {
            "summary": summary.model_dump(mode="json"),
            "scan": scan.model_dump(mode="json"),
            "files": files,
            "index_matches": [match.model_dump(mode="json") for match in indexed],
        }

    def _prompt(self, request: WorkspaceCopilotTaskRequest, context: dict[str, Any]) -> str:
        return (
            "You are Edison Code Space Copilot. Work on the selected existing repository only.\n"
            "Return JSON only. Do not use markdown fences.\n"
            "Schema:\n"
            "{\n"
            '  "summary": "short user-facing summary",\n'
            '  "changes": [{"path": "relative/file.ext", "summary": "what changed", "content": "full new file content"}],\n'
            '  "commands": ["detected command to run, optional"],\n'
            '  "followups": ["optional next step"]\n'
            "}\n"
            "Rules:\n"
            "- Include complete file contents, not patches.\n"
            "- Keep paths relative to the repo root.\n"
            "- Create missing files when needed.\n"
            "- Prefer small, working changes and use the repo's existing stack.\n"
            "- Only suggest commands that are normal repo commands such as tests/builds.\n\n"
            f"User instruction:\n{request.instruction.strip()}\n\n"
            f"Workspace context JSON:\n{json.dumps(context, indent=2)[:50000]}\n"
        )

    def _apply_changes(
        self,
        plan: dict[str, Any],
        request: WorkspaceCopilotTaskRequest,
    ) -> list[WorkspaceCopilotChange]:
        changes: list[WorkspaceCopilotChange] = []
        raw_changes = plan.get("changes") if isinstance(plan.get("changes"), list) else []
        for item in raw_changes[:20]:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip().lstrip("/")
            content = item.get("content")
            if not path or not isinstance(content, str):
                continue
            summary = str(item.get("summary") or "")
            try:
                preview = self.workspace.preview_patch(
                    WorkspacePatchRequest(path=path, proposed_content=content, summary=summary)
                )
                if request.auto_apply:
                    result = self.workspace.apply_patch(
                        WorkspacePatchApplyRequest(
                            path=path,
                            proposed_content=content,
                            summary=summary,
                            expected_sha256=preview.current_sha256,
                            approved=True,
                        )
                    )
                    changes.append(
                        WorkspaceCopilotChange(
                            path=path,
                            summary=summary,
                            applied=True,
                            preview=result.preview,
                            file=result.file,
                        )
                    )
                else:
                    changes.append(WorkspaceCopilotChange(path=path, summary=summary, preview=preview))
            except (WorkspaceAccessError, WorkspaceNotFoundError, WorkspaceUnsupportedFileError, WorkspacePatchConflictError) as error:
                changes.append(WorkspaceCopilotChange(path=path, summary=summary, error=str(error)))
        return changes

    def _run_commands(
        self,
        plan: dict[str, Any],
        request: WorkspaceCopilotTaskRequest,
        job: JobRecord,
    ):
        if not request.run_commands:
            return []
        results = []
        raw_commands = plan.get("commands") if isinstance(plan.get("commands"), list) else []
        for command in [str(item).strip() for item in raw_commands if str(item).strip()][:4]:
            try:
                results.append(
                    self.workspace.run_command(
                        WorkspaceCommandRunRequest(command=command, cwd=".", timeout_seconds=180, approved=True),
                        job,
                    )
                )
            except (WorkspaceCommandNotAllowedError, WorkspaceAccessError, WorkspaceNotFoundError):
                continue
        return results


def _parse_plan(content: str) -> dict[str, Any]:
    for candidate in _json_candidates(content):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _json_candidates(content: str) -> list[str]:
    candidates = []
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", content, flags=re.DOTALL)
    candidates.extend(fenced)
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(content[start : end + 1])
    return candidates


def _fallback_plan(request: WorkspaceCopilotTaskRequest, model_content: str, finish_reason: str) -> dict[str, Any]:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", request.instruction.lower()).strip("-")[:48] or "task"
    content = (
        f"# Code Space Task\n\n"
        f"Instruction:\n\n{request.instruction.strip()}\n\n"
        "## Status\n\n"
        "Edison could not get a structured patch from the selected local coding model yet.\n\n"
        f"- Model finish reason: `{finish_reason}`\n"
        "- Configure the coding model endpoint, then rerun this task to generate code edits.\n\n"
        "## Model Response\n\n"
        f"{model_content.strip()[:4000] or 'No response'}\n"
    )
    return {
        "summary": "Created a Code Space task note because the coding model did not return structured edits.",
        "changes": [
            {
                "path": f"edison-copilot/{slug}.md",
                "summary": "Task note for rerunning once the coding model endpoint is ready.",
                "content": content,
            }
        ],
        "commands": [],
        "followups": ["Configure the local coding model endpoint and rerun this Code Space task."],
    }


def _result_status(finish_reason: str, changes: list[WorkspaceCopilotChange]) -> Literal["complete", "setup_required", "error"]:
    if any(change.error for change in changes):
        return "error"
    if finish_reason == "not_configured":
        return "setup_required"
    return "complete"


def _default_summary(finish_reason: str) -> str:
    if finish_reason == "not_configured":
        return "Coding model endpoint is not configured yet."
    return "Code Space Copilot produced a task result."

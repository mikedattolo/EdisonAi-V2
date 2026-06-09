"""Edison Code Agent: an iterative, tool-using coding agent over a workspace root.

Unlike the single-shot WorkspaceCopilot, this runs a ReAct-style loop
(model -> one JSON action -> execute -> observe -> repeat) and streams its
thinking, edits, and command runs as Server-Sent Events until the task is done
or a budget is hit. Edits apply automatically (sha-guarded); commands require
inline user approval unless auto-run is enabled. The default root is the Edison
app itself, so the agent can modify its own source.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from edison_core.schemas import (
    AgentRunCreate,
    AgentRunEventCreate,
    AgentRunEventKind,
    AgentRunStatus,
    AgentRunStatusUpdate,
    ChatMode,
    InferenceRequest,
    WorkspaceAgentStartRequest,
    WorkspaceIndexSearchRequest,
    WorkspacePatchApplyRequest,
    WorkspacePatchRequest,
    WorkspaceSearchRequest,
)
from edison_core.services.agent_run_store import AgentRunStore
from edison_core.services.model_gateway import ModelGateway
from edison_core.services.workspace_tools import (
    WorkspaceAccessError,
    WorkspaceNotFoundError,
    WorkspacePatchConflictError,
    WorkspaceTools,
    WorkspaceUnsupportedFileError,
    _is_safe_workspace_command,
)


HEARTBEAT_SECONDS = 10
APPROVAL_TIMEOUT_SECONDS = 600
MAX_OBSERVATION_CHARS = 6000
MAX_TRANSCRIPT_MESSAGES = 40
StreamEvent = tuple[str, dict[str, Any]]


@dataclass
class _RunControl:
    approval_event: threading.Event = field(default_factory=threading.Event)
    pending_step_id: str | None = None
    decision: bool | None = None
    cancelled: bool = False


class AgentRunCoordinator:
    """Thread-safe registry that lets the control endpoint signal a running loop."""

    def __init__(self) -> None:
        self._runs: dict[str, _RunControl] = {}
        self._lock = threading.Lock()

    def register(self, run_id: str) -> _RunControl:
        with self._lock:
            control = _RunControl()
            self._runs[run_id] = control
            return control

    def get(self, run_id: str) -> _RunControl | None:
        with self._lock:
            return self._runs.get(run_id)

    def begin_approval(self, run_id: str, step_id: str) -> None:
        with self._lock:
            control = self._runs.get(run_id)
            if control is not None:
                control.pending_step_id = step_id
                control.decision = None
                control.approval_event.clear()

    def submit_decision(self, run_id: str, step_id: str | None, approved: bool) -> bool:
        with self._lock:
            control = self._runs.get(run_id)
            if control is None or control.pending_step_id is None:
                return False
            if step_id and step_id != control.pending_step_id:
                return False
            control.decision = approved
            control.approval_event.set()
            return True

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            control = self._runs.get(run_id)
            if control is None:
                return False
            control.cancelled = True
            control.approval_event.set()
            return True

    def cleanup(self, run_id: str) -> None:
        with self._lock:
            self._runs.pop(run_id, None)


class WorkspaceAgent:
    def __init__(self, gateway: ModelGateway, store: AgentRunStore, coordinator: AgentRunCoordinator) -> None:
        self.gateway = gateway
        self.store = store
        self.coordinator = coordinator

    def stream(self, workspace: WorkspaceTools, request: WorkspaceAgentStartRequest) -> Iterator[StreamEvent]:
        root = workspace.root
        run = self.store.create_run(
            AgentRunCreate(
                title=_title_from_task(request.task),
                prompt=request.task,
                mode=ChatMode.AGENT,
                conversation_id=request.conversation_id,
                metadata={"root_id": request.root_id, "source": "code-agent"},
            ),
            status=AgentRunStatus.RUNNING,
        )
        run_id = run.id
        control = self.coordinator.register(run_id)
        changed_files: dict[str, dict[str, Any]] = {}
        last_summary = ""
        step = 0
        final_status = "complete"

        try:
            checkpoint = _git_checkpoint(root)
            yield (
                "start",
                {
                    "run_id": run_id,
                    "root_id": request.root_id,
                    "task": request.task,
                    "checkpoint": checkpoint,
                    "auto_run_commands": request.auto_run_commands,
                },
            )
            self.store.add_event(
                run_id,
                AgentRunEventCreate(
                    kind=AgentRunEventKind.STATUS,
                    title="Agent started",
                    body=request.task[:500],
                    metadata={"checkpoint": checkpoint, "root_id": request.root_id},
                ),
            )

            transcript = self._initial_messages(workspace, request)

            while step < request.max_steps:
                if control.cancelled:
                    break
                step += 1
                self._set_progress(run_id, step, request.max_steps)

                try:
                    _selection, inference = self.gateway.complete(
                        InferenceRequest(
                            mode=ChatMode.CODING,
                            preferred_model=request.preferred_model,
                            prompt=request.task,
                            metadata={
                                "source": "code-agent",
                                "messages": transcript,
                                "response_format": {"type": "json_object"},
                                "timeout_seconds": 220,
                            },
                        )
                    )
                except Exception as error:  # noqa: BLE001 - surface model/transport errors to the stream
                    yield ("error", {"detail": f"Model call failed: {error}"})
                    final_status = "error"
                    last_summary = f"Model call failed: {error}"
                    break

                if inference.finish_reason == "not_configured":
                    yield ("error", {"detail": inference.content})
                    final_status = "error"
                    last_summary = inference.content
                    break

                transcript.append({"role": "assistant", "content": inference.content[:6000]})
                action = _parse_action(inference.content)

                if not action or not isinstance(action.get("action"), str):
                    transcript.append(
                        {
                            "role": "user",
                            "content": (
                                "Your last reply was not a single valid JSON action object. "
                                "Respond with one JSON object that includes an \"action\" field."
                            ),
                        }
                    )
                    transcript = _trim_transcript(transcript)
                    continue

                thought = str(action.get("thought") or "").strip()
                if thought:
                    yield ("thought", {"text": thought, "step": step})
                    self.store.add_event(
                        run_id,
                        AgentRunEventCreate(kind=AgentRunEventKind.THOUGHT, title=f"Step {step}", body=thought[:1200]),
                    )

                name = str(action["action"]).strip()
                yield ("action", {"action": name, "step": step, "args": _summarize_args(action)})
                self.store.add_event(
                    run_id,
                    AgentRunEventCreate(
                        kind=AgentRunEventKind.TOOL_CALL,
                        title=f"{name}",
                        body=json.dumps(_summarize_args(action))[:500],
                        metadata={"step": step},
                    ),
                )

                if name == "finish":
                    last_summary = str(action.get("summary") or "Task complete.").strip()
                    final_status = "complete"
                    break

                # Execute the action; yields any UI events and returns an observation string.
                observation = ""
                for event in self._execute(workspace, root, request, run_id, control, step, name, action, changed_files):
                    if event[0] == "__observation__":
                        observation = event[1]["text"]
                    else:
                        yield event

                if control.cancelled:
                    break

                transcript.append({"role": "user", "content": f"OBSERVATION (step {step}):\n{observation}"[:MAX_OBSERVATION_CHARS]})
                transcript = _trim_transcript(transcript)
            else:
                # Loop ran out of steps without a finish action.
                final_status = "incomplete"
                last_summary = last_summary or (
                    f"Reached the step budget ({request.max_steps}) before finishing. "
                    "Send the agent another message to continue."
                )

            if control.cancelled:
                self.store.update_run_status(
                    run_id,
                    AgentRunStatusUpdate(status=AgentRunStatus.CANCELLED, current_step="Stopped by user"),
                )
                yield (
                    "done",
                    {
                        "status": "cancelled",
                        "summary": last_summary or "Stopped before completion.",
                        "changed_files": list(changed_files.values()),
                        "steps": step,
                    },
                )
                return

            store_status = {
                "complete": AgentRunStatus.COMPLETED,
                "incomplete": AgentRunStatus.WAITING_FOR_APPROVAL,
                "error": AgentRunStatus.FAILED,
            }.get(final_status, AgentRunStatus.COMPLETED)
            self.store.update_run_status(
                run_id,
                AgentRunStatusUpdate(
                    status=store_status,
                    current_step=last_summary[:200] or "Finished",
                    progress_percent=100 if final_status == "complete" else None,
                ),
            )
            self.store.add_event(
                run_id,
                AgentRunEventCreate(
                    kind=AgentRunEventKind.STATUS if final_status != "error" else AgentRunEventKind.ERROR,
                    title="Agent finished" if final_status != "error" else "Agent failed",
                    body=last_summary[:1200],
                    metadata={"changed_file_count": len(changed_files)},
                ),
            )
            yield (
                "done",
                {
                    "status": final_status,
                    "summary": last_summary or "Done.",
                    "changed_files": list(changed_files.values()),
                    "steps": step,
                },
            )
        except Exception as error:  # noqa: BLE001 - never leak an unstreamed exception
            try:
                self.store.update_run_status(
                    run_id,
                    AgentRunStatusUpdate(status=AgentRunStatus.FAILED, current_step=str(error)[:200]),
                )
            except Exception:  # noqa: BLE001
                pass
            yield ("error", {"detail": f"Agent run failed: {error}"})
            yield (
                "done",
                {
                    "status": "error",
                    "summary": f"Agent run failed: {error}",
                    "changed_files": list(changed_files.values()),
                    "steps": step,
                },
            )
        finally:
            self.coordinator.cleanup(run_id)

    def _execute(
        self,
        workspace: WorkspaceTools,
        root: Path,
        request: WorkspaceAgentStartRequest,
        run_id: str,
        control: _RunControl,
        step: int,
        name: str,
        action: dict[str, Any],
        changed_files: dict[str, dict[str, Any]],
    ) -> Iterator[StreamEvent]:
        if name == "read_file":
            path = str(action.get("path") or "").strip()
            if not path:
                yield ("__observation__", {"text": "read_file requires a 'path'."})
                return
            try:
                record = workspace.read_file(path)
            except (WorkspaceAccessError, WorkspaceNotFoundError, WorkspaceUnsupportedFileError) as error:
                yield ("__observation__", {"text": f"read_file failed: {error}"})
                return
            yield ("observation", {"text": f"Read {record.path} ({len(record.content)} chars)", "step": step, "kind": "read", "path": record.path})
            body = record.content[:MAX_OBSERVATION_CHARS]
            suffix = "\n...[truncated]" if len(record.content) > MAX_OBSERVATION_CHARS else ""
            yield ("__observation__", {"text": f"FILE {record.path} (language={record.language}):\n{body}{suffix}"})
            return

        if name == "list_dir":
            path = str(action.get("path") or "").strip()
            try:
                entries = workspace.list_directory(path, limit=200)
            except (WorkspaceAccessError, WorkspaceNotFoundError) as error:
                yield ("__observation__", {"text": f"list_dir failed: {error}"})
                return
            listing = "\n".join(f"{getattr(entry, 'kind', 'file')}\t{entry.path}" for entry in entries)
            yield ("observation", {"text": f"Listed {path or '.'} ({len(entries)} entries)", "step": step, "kind": "list", "path": path or "."})
            yield ("__observation__", {"text": f"DIRECTORY {path or '.'}:\n{listing[:MAX_OBSERVATION_CHARS]}"})
            return

        if name == "search":
            query = str(action.get("query") or "").strip()
            if not query:
                yield ("__observation__", {"text": "search requires a 'query'."})
                return
            try:
                matches = workspace.search(WorkspaceSearchRequest(query=query, max_results=14, include_content=True))
            except (WorkspaceAccessError, WorkspaceNotFoundError) as error:
                yield ("__observation__", {"text": f"search failed: {error}"})
                return
            rendered = "\n".join(
                f"{match.path}:{getattr(match, 'line_number', '') or ''} {getattr(match, 'snippet', '') or ''}".strip()
                for match in matches
            )
            yield ("observation", {"text": f"Search \"{query}\": {len(matches)} matches", "step": step, "kind": "search"})
            yield ("__observation__", {"text": f"SEARCH \"{query}\" ({len(matches)} matches):\n{rendered[:MAX_OBSERVATION_CHARS] or 'No matches.'}"})
            return

        if name == "edit_file":
            path = str(action.get("path") or "").strip()
            content = action.get("content")
            summary = str(action.get("summary") or "").strip()
            if not path or not isinstance(content, str):
                yield ("__observation__", {"text": "edit_file requires 'path' and full 'content' (a string)."})
                return
            try:
                preview = workspace.preview_patch(
                    WorkspacePatchRequest(path=path, proposed_content=content, summary=summary, create_if_missing=True)
                )
                workspace.apply_patch(
                    WorkspacePatchApplyRequest(
                        path=path,
                        proposed_content=content,
                        summary=summary,
                        create_if_missing=True,
                        expected_sha256=preview.current_sha256,
                        approved=True,
                    )
                )
            except (
                WorkspaceAccessError,
                WorkspaceNotFoundError,
                WorkspaceUnsupportedFileError,
                WorkspacePatchConflictError,
            ) as error:
                yield ("__observation__", {"text": f"edit_file failed: {error}"})
                return
            changed_files[preview.path] = {
                "path": preview.path,
                "additions": preview.additions,
                "deletions": preview.deletions,
            }
            yield (
                "file_edit",
                {
                    "path": preview.path,
                    "summary": summary,
                    "additions": preview.additions,
                    "deletions": preview.deletions,
                    "diff": preview.diff[:8000],
                    "step": step,
                },
            )
            self.store.add_event(
                run_id,
                AgentRunEventCreate(
                    kind=AgentRunEventKind.TOOL_RESULT,
                    title=f"Edited {preview.path}",
                    body=f"+{preview.additions} -{preview.deletions}: {summary}"[:500],
                    metadata={"path": preview.path, "step": step},
                ),
            )
            yield ("__observation__", {"text": f"Applied edit to {preview.path} (+{preview.additions} -{preview.deletions})."})
            return

        if name == "run_command":
            yield from self._run_command(root, request, run_id, control, step, action)
            return

        yield ("__observation__", {"text": f"Unknown action '{name}'. Valid actions: read_file, list_dir, search, edit_file, run_command, finish."})

    def _run_command(
        self,
        root: Path,
        request: WorkspaceAgentStartRequest,
        run_id: str,
        control: _RunControl,
        step: int,
        action: dict[str, Any],
    ) -> Iterator[StreamEvent]:
        command = str(action.get("command") or "").strip()
        cwd = str(action.get("cwd") or ".").strip() or "."
        reason = str(action.get("reason") or "").strip()
        if not command:
            yield ("__observation__", {"text": "run_command requires a 'command'."})
            return
        if not _is_safe_workspace_command(command):
            yield ("command_skipped", {"command": command, "reason": "Blocked by safety policy", "step": step})
            yield (
                "__observation__",
                {
                    "text": (
                        f"Command '{command}' is not permitted. Only test runners (pytest, npm test), "
                        "builds (npm run ...), and read-only git (status/diff/log) are allowed."
                    )
                },
            )
            return

        approved: bool
        if request.auto_run_commands:
            approved = True
        else:
            step_id = f"{run_id}:{step}"
            self.coordinator.begin_approval(run_id, step_id)
            self.store.update_run_status(
                run_id,
                AgentRunStatusUpdate(
                    status=AgentRunStatus.WAITING_FOR_APPROVAL,
                    current_step=f"Awaiting approval: {command}",
                ),
            )
            self.store.add_event(
                run_id,
                AgentRunEventCreate(kind=AgentRunEventKind.APPROVAL, title="Command needs approval", body=command[:300]),
            )
            yield (
                "command_request",
                {"run_id": run_id, "step_id": step_id, "command": command, "cwd": cwd, "reason": reason, "step": step},
            )

            decision: bool | None = None
            waited = 0.0
            while waited < APPROVAL_TIMEOUT_SECONDS:
                if control.cancelled:
                    return
                if control.approval_event.wait(timeout=HEARTBEAT_SECONDS):
                    if control.cancelled:
                        return
                    decision = bool(control.decision)
                    break
                waited += HEARTBEAT_SECONDS
                yield ("heartbeat", {"step": step})
            approved = bool(decision)
            self.store.update_run_status(
                run_id,
                AgentRunStatusUpdate(status=AgentRunStatus.RUNNING, current_step="Running"),
            )

        if not approved:
            yield ("command_skipped", {"command": command, "reason": "Declined", "step": step})
            yield (
                "__observation__",
                {"text": f"The user declined to run '{command}'. Continue without it or take a different approach."},
            )
            return

        yield ("status", {"message": f"Running: {command}", "step": step})
        result = _run_command_safe(root, command, cwd, timeout=request_command_timeout(command))
        yield ("command_result", {"command": command, "cwd": cwd, "step": step, **result})
        self.store.add_event(
            run_id,
            AgentRunEventCreate(
                kind=AgentRunEventKind.TOOL_RESULT,
                title=f"Ran {command}",
                body=f"exit={result.get('exit_code')} status={result.get('status')}"[:300],
                metadata={"step": step},
            ),
        )
        yield (
            "__observation__",
            {
                "text": (
                    f"Command '{command}' finished: status={result.get('status')} exit={result.get('exit_code')}\n"
                    f"STDOUT:\n{result.get('stdout', '')[:3000]}\n"
                    f"STDERR:\n{result.get('stderr', '')[:1500]}"
                )
            },
        )

    def _initial_messages(self, workspace: WorkspaceTools, request: WorkspaceAgentStartRequest) -> list[dict[str, str]]:
        context: dict[str, Any] = {}
        try:
            context["summary"] = workspace.summarize().model_dump(mode="json")
        except Exception:  # noqa: BLE001
            context["summary"] = {}
        try:
            scan = workspace.scan().model_dump(mode="json")
            context["commands"] = scan.get("commands", [])
            context["stacks"] = scan.get("stacks", [])
            context["test_targets"] = scan.get("test_targets", [])
        except Exception:  # noqa: BLE001
            pass
        try:
            matches = workspace.search_index(WorkspaceIndexSearchRequest(query=request.task, max_results=10))
            context["relevant_files"] = [match.path for match in matches]
        except Exception:  # noqa: BLE001
            context["relevant_files"] = []

        root_label = "the Edison app itself (you are editing your own source)" if request.root_id == "app" else f"project '{request.root_id}'"
        # NOTE: use replace (not .format) - the prompt contains literal JSON braces.
        system = AGENT_SYSTEM_PROMPT.replace("{root_label}", root_label)
        user = (
            f"TASK:\n{request.task.strip()}\n\n"
            f"WORKSPACE CONTEXT (root={request.root_id}):\n{json.dumps(context, indent=2)[:8000]}\n\n"
            "Begin now. Respond with exactly one JSON action."
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def _set_progress(self, run_id: str, step: int, max_steps: int) -> None:
        percent = min(95, int((step / max(max_steps, 1)) * 90) + 5)
        try:
            self.store.update_run_status(
                run_id,
                AgentRunStatusUpdate(
                    status=AgentRunStatus.RUNNING,
                    current_step=f"Step {step}",
                    progress_percent=percent,
                ),
            )
        except Exception:  # noqa: BLE001
            pass


AGENT_SYSTEM_PROMPT = (
    "You are Edison Code Agent, an autonomous coding agent running inside the Edison app on Mike's local AI PC. "
    "You operate ONLY within the selected workspace root: {root_label}. Be precise and careful.\n\n"
    "Work step by step. On EACH turn respond with EXACTLY ONE JSON object describing your next action - no prose, "
    "no markdown fences, no extra text. Keep going until the task is fully complete; do not stop early. Use the "
    "\"finish\" action only when the work is genuinely done (and verified when relevant).\n\n"
    "Action object schema (one per turn):\n"
    '{"thought": "<1-3 sentence reasoning>", "action": "read_file|list_dir|search|edit_file|run_command|finish", ...}\n'
    "Fields by action:\n"
    '- read_file: {"path": "relative/path"}\n'
    '- list_dir:  {"path": "relative/dir"}   (use "" for the root)\n'
    '- search:    {"query": "text or symbol to find"}\n'
    '- edit_file: {"path": "relative/path", "content": "<COMPLETE new file content>", "summary": "<short what changed>"}\n'
    '- run_command: {"command": "<cmd>", "cwd": "relative dir or .", "reason": "<why>"}\n'
    '- finish:    {"summary": "<what changed, files touched, how to verify>"}\n\n'
    "Rules:\n"
    "- edit_file REPLACES the entire file with \"content\". Read a file before editing it (unless creating a new one). "
    "Always provide complete, working file contents - never partial snippets, placeholders, or \"...\".\n"
    "- Match the existing code style. Make focused changes and verify as you go.\n"
    "- You may ONLY run safe commands: test runners (pytest, npm test), builds (npm run ...), and read-only git "
    "(status/diff/log). Anything else is blocked. Commands require the user's approval before running.\n"
    "- Frontend edits (apps/web) need a build; backend edits need an Edison restart to take effect - mention this in finish.\n"
    "- If a step fails, read the error and adapt; do not repeat the same failing action.\n"
)


def request_command_timeout(command: str) -> int:
    lowered = command.lower()
    if "build" in lowered:
        return 600
    if "pytest" in lowered or "test" in lowered:
        return 420
    return 240


def _run_command_safe(root: Path, command: str, cwd: str, timeout: int = 240) -> dict[str, Any]:
    cwd_path = (root / cwd).resolve() if cwd not in ("", ".") else root
    try:
        cwd_path.relative_to(root.resolve())
    except ValueError:
        return {"exit_code": None, "status": "error", "stdout": "", "stderr": f"cwd outside workspace: {cwd}", "duration_ms": 0}
    if not cwd_path.is_dir():
        return {"exit_code": None, "status": "error", "stdout": "", "stderr": f"cwd not found: {cwd}", "duration_ms": 0}
    started = time.monotonic()
    try:
        completed = subprocess.run(
            shlex.split(command),
            cwd=cwd_path,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "exit_code": completed.returncode,
            "status": "complete" if completed.returncode == 0 else "error",
            "stdout": _truncate(completed.stdout, 8000),
            "stderr": _truncate(completed.stderr, 4000),
            "duration_ms": duration_ms,
        }
    except subprocess.TimeoutExpired as error:
        return {
            "exit_code": None,
            "status": "timeout",
            "stdout": _truncate(error.stdout or "", 4000),
            "stderr": _truncate(error.stderr or "", 2000),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    except Exception as error:  # noqa: BLE001
        return {"exit_code": None, "status": "error", "stdout": "", "stderr": str(error)[:1000], "duration_ms": 0}


def _git_checkpoint(root: Path) -> dict[str, Any]:
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10)
        sha = head.stdout.strip() if head.returncode == 0 else None
        status = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, timeout=10)
        dirty = bool(status.stdout.strip()) if status.returncode == 0 else None
        return {"head": sha, "dirty": dirty}
    except Exception:  # noqa: BLE001
        return {"head": None, "dirty": None}


def _parse_action(content: str) -> dict[str, Any] | None:
    candidates: list[str] = list(re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", content, flags=re.DOTALL))
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(content[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _summarize_args(action: dict[str, Any]) -> dict[str, Any]:
    keep = {}
    for key in ("path", "query", "command", "cwd", "reason", "summary"):
        value = action.get(key)
        if isinstance(value, str) and value.strip():
            keep[key] = value[:240]
    if isinstance(action.get("content"), str):
        keep["content_chars"] = len(action["content"])
    return keep


def _trim_transcript(transcript: list[dict[str, str]]) -> list[dict[str, str]]:
    if len(transcript) <= MAX_TRANSCRIPT_MESSAGES:
        return transcript
    head = transcript[:2]  # system + original task
    tail = transcript[-(MAX_TRANSCRIPT_MESSAGES - 3) :]
    notice = {"role": "user", "content": "[earlier steps trimmed to save context]"}
    return head + [notice] + tail


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def _title_from_task(task: str) -> str:
    flat = " ".join(task.split())
    return f"{flat[:57]}..." if len(flat) > 60 else (flat or "Code agent run")

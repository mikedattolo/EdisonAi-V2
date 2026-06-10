"""Edison Code Agent: an iterative, tool-using coding agent over a workspace root.

Unlike the single-shot WorkspaceCopilot, this runs a ReAct-style loop
(model -> one JSON action -> execute -> observe -> repeat) and streams its
thinking, edits, and command runs as Server-Sent Events until the task is done
or a budget is hit. Edits apply automatically (sha-guarded); commands require
inline user approval unless auto-run is enabled. The default root is the Edison
app itself, so the agent can modify its own source.
"""

from __future__ import annotations

import concurrent.futures
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
            recent_sigs: list[str] = []

            while step < request.max_steps:
                if control.cancelled:
                    break
                step += 1
                self._set_progress(run_id, step, request.max_steps)

                # Run the (blocking) model call in a thread and emit heartbeats while waiting, so the
                # SSE stream never goes silent long enough for the proxy/browser to drop it ("network error").
                pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                future = pool.submit(
                    self.gateway.complete,
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
                    ),
                )
                inference = None
                model_error: Exception | None = None
                while True:
                    try:
                        _selection, inference = future.result(timeout=HEARTBEAT_SECONDS)
                        break
                    except concurrent.futures.TimeoutError:
                        if control.cancelled:
                            break
                        yield ("heartbeat", {"step": step, "phase": "thinking"})
                    except Exception as error:  # noqa: BLE001 - surface model/transport errors to the stream
                        model_error = error
                        break
                pool.shutdown(wait=False)
                if control.cancelled:
                    break
                if model_error is not None:
                    yield ("error", {"detail": f"Model call failed: {model_error}"})
                    final_status = "error"
                    last_summary = f"Model call failed: {model_error}"
                    break
                if inference is None:
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

                signature = _action_signature(name, action)
                recent_sigs.append(signature)
                recent_sigs = recent_sigs[-6:]
                repeats = sum(1 for item in recent_sigs if item == signature)
                if repeats >= 4:
                    final_status = "incomplete"
                    last_summary = (
                        "Stopped: the agent repeated the same step several times without progress. "
                        "Re-run with a more specific instruction, or check whether the edit already applied."
                    )
                    yield ("status", {"message": "Stopped - repeated the same step without progress."})
                    break

                # Execute the action; yields any UI events and returns an observation string.
                observation = ""
                edits_before = len(changed_files)
                for event in self._execute(workspace, root, request, run_id, control, step, name, action, changed_files):
                    if event[0] == "__observation__":
                        observation = event[1]["text"]
                    else:
                        yield event

                if control.cancelled:
                    break

                steer = ""
                if repeats == 3:
                    steer += (
                        "\n\nNOTE: you have repeated this exact action. If the edit already applied (see the diffs "
                        "above), call finish. If an edit keeps failing to match, read the exact lines with read_file "
                        "(start_line/end_line) and copy them verbatim into old_text."
                    )
                if len(changed_files) > edits_before:
                    steer += "\n\nThe edit was applied successfully. If the task is now complete, respond with the finish action."
                transcript.append(
                    {"role": "user", "content": f"OBSERVATION (step {step}):\n{observation}{steer}"[:MAX_OBSERVATION_CHARS]}
                )
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
            file_lines = record.content.splitlines()
            total = len(file_lines)
            start = _coerce_int(action.get("start_line"))
            end = _coerce_int(action.get("end_line"))
            if start or end:
                start_idx = max((start or 1) - 1, 0)
                end_idx = min(end or (start_idx + 220), total)
                if end_idx <= start_idx:
                    end_idx = min(start_idx + 220, total)
            else:
                start_idx = 0
                end_idx = min(220, total)
            window = file_lines[start_idx:end_idx]
            numbered = "\n".join(f"{start_idx + offset + 1}\t{text}" for offset, text in enumerate(window))
            if len(numbered) > MAX_OBSERVATION_CHARS:
                numbered = numbered[:MAX_OBSERVATION_CHARS] + "\n...[truncated - request a narrower line range]"
            more = ""
            if end_idx < total:
                more = f"\n... {total - end_idx} more lines below. Use {{\"start_line\": {end_idx + 1}}} to continue."
            yield ("observation", {"text": f"Read {record.path} lines {start_idx + 1}-{end_idx}/{total}", "step": step, "kind": "read", "path": record.path})
            yield (
                "__observation__",
                {"text": f"FILE {record.path} (lines {start_idx + 1}-{end_idx} of {total}, language={record.language}):\n{numbered}{more}"},
            )
            return

        if name == "replace":
            path = str(action.get("path") or "").strip()
            old_text = action.get("old_text")
            new_text = action.get("new_text")
            summary = str(action.get("summary") or "").strip()
            if not path or not isinstance(old_text, str) or not isinstance(new_text, str):
                yield ("__observation__", {"text": "replace requires 'path', 'old_text', and 'new_text' (strings)."})
                return
            if not old_text:
                yield ("__observation__", {"text": "replace 'old_text' must not be empty. Use edit_file to create a new file."})
                return
            try:
                record = workspace.read_file(path)
            except (WorkspaceAccessError, WorkspaceNotFoundError, WorkspaceUnsupportedFileError) as error:
                yield ("__observation__", {"text": f"replace could not read {path}: {error}"})
                return
            new_content, status, match_note = _compute_replacement(record.content, old_text, new_text)
            if new_content is None:
                if status == "ambiguous":
                    yield ("__observation__", {"text": f"replace: 'old_text' matches {match_note} places in {path}. Add more surrounding lines so it matches exactly once."})
                else:
                    yield ("__observation__", {"text": f"replace: 'old_text' was not found in {path}. Open the exact lines with read_file (start_line/end_line) and copy them verbatim into old_text (indentation included)."})
                return
            try:
                preview = workspace.preview_patch(
                    WorkspacePatchRequest(path=path, proposed_content=new_content, summary=summary, create_if_missing=False)
                )
                workspace.apply_patch(
                    WorkspacePatchApplyRequest(
                        path=path,
                        proposed_content=new_content,
                        summary=summary,
                        create_if_missing=False,
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
                yield ("__observation__", {"text": f"replace failed to apply: {error}"})
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
            yield (
                "__observation__",
                {
                    "text": (
                        f"Replaced text in {preview.path} (+{preview.additions} -{preview.deletions}). "
                        f"The change is applied to disk. Diff:\n{preview.diff[:1500]}\n"
                        "Do NOT re-read the file to confirm - the diff above is the confirmation. "
                        "If the task is complete, respond with the finish action."
                    )
                },
            )
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
            matches = _grep_workspace(workspace.root, query, max_results=40)
            rendered = "\n".join(matches)
            yield ("observation", {"text": f"Search \"{query}\": {len(matches)} matches", "step": step, "kind": "search"})
            yield (
                "__observation__",
                {
                    "text": (
                        f"SEARCH \"{query}\" - {len(matches)} matches (path:line:text):\n"
                        + (
                            rendered[:MAX_OBSERVATION_CHARS]
                            if rendered
                            else "No matches. Try a single distinctive word or an identifier, or open a file from the REPO FILE TREE directly."
                        )
                    )
                },
            )
            return

        if name == "edit_file":
            path = str(action.get("path") or "").strip()
            content = action.get("content")
            summary = str(action.get("summary") or "").strip()
            if not path or not isinstance(content, str):
                yield ("__observation__", {"text": "edit_file requires 'path' and full 'content' (a string)."})
                return
            try:
                existing_content = workspace.read_file(path).content
            except (WorkspaceAccessError, WorkspaceNotFoundError, WorkspaceUnsupportedFileError):
                existing_content = None
            if existing_content is not None:
                old_lines = len(existing_content.splitlines())
                new_lines = len(content.splitlines())
                if old_lines >= 25 and new_lines < max(10, int(old_lines * 0.6)):
                    yield (
                        "__observation__",
                        {
                            "text": (
                                f"edit_file refused: replacing {path} would shrink it from {old_lines} to {new_lines} "
                                "lines, which looks like a truncated rewrite. To change PART of an existing file, use the "
                                "replace action (old_text -> new_text). edit_file is only for a new file or a complete rewrite."
                            )
                        },
                    )
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
            yield (
                "__observation__",
                {
                    "text": (
                        f"Applied edit to {preview.path} (+{preview.additions} -{preview.deletions}). "
                        f"The change is applied to disk. Diff:\n{preview.diff[:1500]}\n"
                        "Do NOT re-read the file to confirm - the diff above is the confirmation. "
                        "If the task is complete, respond with the finish action."
                    )
                },
            )
            return

        if name == "run_command":
            yield from self._run_command(root, request, run_id, control, step, action)
            return

        yield ("__observation__", {"text": f"Unknown action '{name}'. Valid actions: read_file, list_dir, search, replace, edit_file, run_command, finish."})

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
        stacks: Any = []
        commands: list[Any] = []
        try:
            scan = workspace.scan().model_dump(mode="json")
            stacks = scan.get("stacks", [])
            commands = [
                command.get("command") if isinstance(command, dict) else command
                for command in (scan.get("commands") or [])
            ][:10]
        except Exception:  # noqa: BLE001
            pass
        try:
            file_tree = _repo_file_tree(workspace.root)
        except Exception:  # noqa: BLE001
            file_tree = []
        try:
            matches = workspace.search_index(WorkspaceIndexSearchRequest(query=request.task, max_results=8))
            relevant = [match.path for match in matches]
        except Exception:  # noqa: BLE001
            relevant = []

        root_label = (
            "the Edison app itself (you are editing your own source)"
            if request.root_id == "app"
            else f"project '{request.root_id}'"
        )
        repo_map = EDISON_REPO_MAP if request.root_id == "app" else ""
        # NOTE: use replace (not .format) - the prompt contains literal JSON braces.
        system = AGENT_SYSTEM_PROMPT.replace("{root_label}", root_label).replace("{repo_map}", repo_map)

        tree_text = "\n".join(file_tree)
        user = (
            f"TASK:\n{request.task.strip()}\n\n"
            f"REPO FILE TREE (root={request.root_id}, {len(file_tree)} files):\n{tree_text[:9000]}\n\n"
            f"Detected stacks: {stacks}\nRunnable commands: {commands}\n"
            f"Index guess at relevant files: {relevant}\n\n"
            "Use the REPO FILE TREE above to open the right files directly, and the search action to locate "
            "identifiers. Then make the change. Respond with exactly one JSON action."
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
    '{"thought": "<1-3 sentence reasoning>", "action": "read_file|list_dir|search|replace|edit_file|run_command|finish", ...}\n'
    "Fields by action:\n"
    '- read_file: {"path": "relative/path", "start_line": <int optional>, "end_line": <int optional>}\n'
    '- list_dir:  {"path": "relative/dir"}   (use "" for the root)\n'
    '- search:    {"query": "word or identifier"}\n'
    '- replace:   {"path": "relative/path", "old_text": "<exact existing snippet>", "new_text": "<replacement>", "summary": "<short>"}\n'
    '- edit_file: {"path": "relative/path", "content": "<COMPLETE new file content>", "summary": "<short what changed>"}\n'
    '- run_command: {"command": "<cmd>", "cwd": "relative dir or .", "reason": "<why>"}\n'
    '- finish:    {"summary": "<what changed, files touched, how to verify>"}\n\n'
    "FINDING CODE (important - this is where agents usually fail):\n"
    "- A REPO FILE TREE is given in the first message. Use it to open the right files DIRECTLY - you usually do not "
    "need to search just to find a path.\n"
    "- The search action is a case-insensitive code grep that returns path:line:text. Search for ONE distinctive word "
    "or identifier, NOT a sentence. Multi-word queries match flexibly across separators, so \"creator studio\" also "
    "matches \"Creator Studio\", \"creator-studio\", \"creator_studio\", and \"creatorStudio\".\n"
    "- Files can be LARGE. read_file returns numbered lines and only a window (~220 lines). To see a specific "
    "section, pass start_line/end_line (use the line numbers from search). Do NOT re-read the same file from the "
    "top repeatedly - page through it with start_line.\n"
    "{repo_map}"
    "EDITING (important):\n"
    "- To change an EXISTING file, use replace: copy the exact current snippet into old_text (it must match exactly "
    "ONCE, including indentation) and put the changed code in new_text. NEVER paste a whole large file into "
    "edit_file.\n"
    "- Use edit_file (full content) ONLY to create a NEW file or rewrite a very small one.\n"
    "- read_file the exact lines first so old_text matches. After an edit, you can read_file again to confirm.\n"
    "Rules:\n"
    "- Match the existing code style. Make focused changes and verify as you go.\n"
    "- You may ONLY run safe commands: test runners (pytest, npm test), builds (npm run ...), and read-only git "
    "(status/diff/log). Anything else is blocked. Commands require the user's approval before running.\n"
    "- Frontend edits (apps/web) need a build; backend edits need an Edison restart to take effect - mention this in finish.\n"
    "- If a step fails, read the error and adapt; do not repeat the same failing action.\n"
)


EDISON_REPO_MAP = (
    "\nEDISON REPO MAP (you are editing this app - use these exact locations):\n"
    "- Frontend is ONE React single-page app. apps/web/src/App.tsx holds ALL views as components: the chat, "
    "CreatorStudioView (Creator Studio), CodeWorkspaceView + CodeAgentPanel (Code Space), MemoryView (Knowledge), "
    "media, gallery, settings. apps/web/src/styles.css holds ALL styling (class-based: .creator-* = Creator Studio, "
    ".code-agent-* = this agent, .message/.composer = chat). apps/web/src/api.ts = API client, "
    "apps/web/src/types.ts = shared types.\n"
    "- Backend is FastAPI under apps/api/edison_core: api/routes_*.py = HTTP routes, services/*.py = logic "
    "(creator_studio.py, knowledge_store.py, workspace_agent.py, model_gateway.py, ...), schemas.py = pydantic "
    "models, main.py = wiring.\n"
    "- Example: 'Creator Studio' UI text/styles live in apps/web/src/App.tsx (search CreatorStudioView) and "
    "apps/web/src/styles.css (the .creator-* rules); its backend is apps/api/edison_core/services/creator_studio.py.\n\n"
)


def request_command_timeout(command: str) -> int:
    lowered = command.lower()
    if "build" in lowered:
        return 600
    if "pytest" in lowered or "test" in lowered:
        return 420
    return 240


_GREP_EXCLUDE_DIRS = (
    ".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".vite", "artifacts",
    "data", "logs", "vendor", "edison-copilot",
)


def _grep_workspace(root: Path, query: str, max_results: int = 40) -> list[str]:
    """Case-insensitive code grep that tolerates phrases and separator/case variants.

    Ranks files by how many query tokens they contain (plus a flexible-phrase bonus),
    with the app source dirs first, so real code beats noisy scripts/docs.
    "creator studio" also finds "Creator Studio", "creator-studio", and "creatorStudio".
    Returns up to ``max_results`` "path:line:text" strings.
    """
    raw_tokens = [token for token in re.split(r"\s+", query.strip()) if token]
    tokens = [re.sub(r"[^A-Za-z0-9]+", "", token) for token in raw_tokens]
    tokens = [token for token in tokens if len(token) >= 3]
    if not tokens:
        fallback = re.sub(r"[^A-Za-z0-9]+", "", query.strip())
        tokens = [fallback] if len(fallback) >= 2 else []
    if not tokens:
        return []

    exclude_args: list[str] = []
    for name in _GREP_EXCLUDE_DIRS:
        exclude_args += ["--exclude-dir", name]

    def _run(mode: str, pattern: str) -> str:
        try:
            completed = subprocess.run(
                ["grep", "-rIn", "-i", mode, *exclude_args, "-e", pattern, "."],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            return completed.stdout
        except Exception:  # noqa: BLE001
            return ""

    patterns: list[tuple[str, str, bool]] = [(token, "-F", False) for token in tokens]
    if len(tokens) >= 2:
        patterns.append(("[ _-]?".join(tokens[:2]), "-E", True))

    file_hits: dict[str, dict[str, Any]] = {}
    for pattern, mode, is_phrase in patterns:
        for line in _run(mode, pattern).splitlines():
            cleaned = line[2:] if line.startswith("./") else line
            parts = cleaned.split(":", 2)
            if len(parts) < 3:
                continue
            fpath, lno, text = parts[0], parts[1], parts[2]
            entry = file_hits.setdefault(fpath, {"tokens": set(), "phrase": False, "lines": []})
            entry["tokens"].add("__phrase__" if is_phrase else pattern)
            if is_phrase:
                entry["phrase"] = True
            sample = f"{fpath}:{lno}:{text.strip()[:140]}"
            if len(entry["lines"]) < 3 and sample not in entry["lines"]:
                entry["lines"].append(sample)

    def _dir_rank(path: str) -> int:
        if path.startswith("apps/web/src/"):
            return 0
        if path.startswith("apps/api/"):
            return 1
        if path.startswith("apps/"):
            return 2
        if path.startswith(("scripts/", "config/")):
            return 3
        return 4

    def _score(item: tuple[str, dict[str, Any]]) -> tuple[int, int, str]:
        path, entry = item
        relevance = len(entry["tokens"]) + (2 if entry["phrase"] else 0)
        return (-relevance, _dir_rank(path), path)

    results: list[str] = []
    for path, entry in sorted(file_hits.items(), key=_score):
        for sample in entry["lines"]:
            results.append(sample[:220])
            if len(results) >= max_results:
                return results
    return results


def _repo_file_tree(root: Path, max_files: int = 700) -> list[str]:
    """A compact list of source file paths (git-tracked first), source dirs ranked first."""
    files: list[str] = []
    try:
        completed = subprocess.run(
            ["git", "ls-files"], cwd=root, capture_output=True, text=True, timeout=15, check=False
        )
        if completed.returncode == 0:
            files = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    except Exception:  # noqa: BLE001
        files = []
    if not files:
        try:
            for path in sorted(root.rglob("*")):
                if not path.is_file():
                    continue
                relative_parts = path.relative_to(root).parts
                if any(part in _GREP_EXCLUDE_DIRS for part in relative_parts):
                    continue
                files.append(path.relative_to(root).as_posix())
                if len(files) >= max_files * 2:
                    break
        except Exception:  # noqa: BLE001
            pass

    image_ext = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".svg", ".pdf", ".lock"}
    drop_prefixes = ("vendor/", "edison-copilot/")
    filtered = [
        path
        for path in files
        if not path.startswith(drop_prefixes) and Path(path).suffix.lower() not in image_ext
    ]

    def _rank(path: str) -> int:
        if path.startswith("apps/web/src/"):
            return 0
        if path.startswith("apps/api/"):
            return 1
        if path.startswith("apps/"):
            return 2
        if path.startswith(("scripts/", "config/")):
            return 3
        return 4

    filtered.sort(key=lambda path: (_rank(path), path))
    return filtered[:max_files]


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


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _action_signature(name: str, action: dict[str, Any]) -> str:
    parts = [name]
    for field in ("path", "query", "command", "start_line", "end_line"):
        value = action.get(field)
        if value is not None and str(value).strip():
            parts.append(f"{field}={str(value)[:120]}")
    old_text = action.get("old_text")
    if isinstance(old_text, str) and old_text:
        parts.append(f"old={old_text[:160]}")
    return "|".join(parts)


def _compute_replacement(content: str, old_text: str, new_text: str) -> tuple[str | None, str, str]:
    """Locate old_text and return the new content, tolerant of CRLF and trailing whitespace.

    Returns (new_content | None, status, note). status is "exact"/"normalized" on success,
    or "ambiguous"/"notfound" on failure (note holds the match count).
    """
    count = content.count(old_text)
    if count == 1:
        return content.replace(old_text, new_text, 1), "exact", "1"
    if count > 1:
        return None, "ambiguous", str(count)

    content_lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    old_lines = old_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while len(old_lines) > 1 and old_lines[-1] == "":
        old_lines = old_lines[:-1]
    if not old_lines or (len(old_lines) == 1 and old_lines[0] == ""):
        return None, "notfound", "0"
    new_lines = new_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    span = len(old_lines)

    for normalize in (lambda line: line.rstrip(), lambda line: line.strip()):
        target = [normalize(line) for line in old_lines]
        haystack = [normalize(line) for line in content_lines]
        hits = [index for index in range(0, len(haystack) - span + 1) if haystack[index : index + span] == target]
        if len(hits) == 1:
            start = hits[0]
            spliced = content_lines[:start] + new_lines + content_lines[start + span :]
            return "\n".join(spliced), "normalized", "1"
        if len(hits) > 1:
            return None, "ambiguous", str(len(hits))
    return None, "notfound", "0"


def _title_from_task(task: str) -> str:
    flat = " ".join(task.split())
    return f"{flat[:57]}..." if len(flat) > 60 else (flat or "Code agent run")

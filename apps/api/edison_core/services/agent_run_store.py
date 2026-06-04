from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from edison_core.database import SQLiteDatabase
from edison_core.schemas import (
    AgentRunCreate,
    AgentRunEventCreate,
    AgentRunEventKind,
    AgentRunEventRecord,
    AgentRunRecord,
    AgentRunStatus,
    AgentRunStatusUpdate,
    AgentRunWithEvents,
    utc_now,
)


class AgentRunNotFoundError(ValueError):
    pass


class AgentRunStore:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def initialize(self) -> None:
        with self.database.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress_percent INTEGER NOT NULL DEFAULT 0,
                    current_step TEXT,
                    conversation_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_run_events (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_agent_runs_updated
                    ON agent_runs(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_agent_run_events_created
                    ON agent_run_events(run_id, created_at ASC);
                """
            )

    def create_run(
        self,
        payload: AgentRunCreate,
        status: AgentRunStatus = AgentRunStatus.PLANNING,
    ) -> AgentRunWithEvents:
        now = utc_now()
        title = payload.title or _title_from_prompt(payload.prompt)
        run = AgentRunRecord(
            id=f"run_{uuid4().hex}",
            title=title,
            prompt=payload.prompt,
            mode=payload.mode,
            status=status,
            progress_percent=8,
            current_step="Planning the request",
            conversation_id=payload.conversation_id,
            metadata=payload.metadata,
            created_at=now,
            updated_at=now,
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs (
                    id, title, prompt, mode, status, progress_percent, current_step,
                    conversation_id, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.title,
                    run.prompt,
                    run.mode.value,
                    run.status.value,
                    run.progress_percent,
                    run.current_step,
                    run.conversation_id,
                    json.dumps(run.metadata),
                    run.created_at.isoformat(),
                    run.updated_at.isoformat(),
                ),
            )
        self.add_event(
            run.id,
            AgentRunEventCreate(
                kind=AgentRunEventKind.STATUS,
                title="Run created",
                body="Edison opened an agent run and attached it to the chat turn.",
                metadata={"status": status.value},
            ),
        )
        self.add_event(
            run.id,
            AgentRunEventCreate(
                kind=AgentRunEventKind.PLAN,
                title="Starter plan",
                body="\n".join(
                    [
                        "1. Read the user request and current Edison context.",
                        "2. Select the right workspace, knowledge, hardware, or media tools.",
                        "3. Execute with visible progress and save results back to chat.",
                    ]
                ),
                metadata={"source": "agent-run-store"},
            ),
        )
        return self.get_run(run.id)

    def list_runs(self, limit: int = 50) -> list[AgentRunRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_runs ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._run_from_row(row) for row in rows]

    def get_run(self, run_id: str) -> AgentRunWithEvents:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
            event_rows = connection.execute(
                "SELECT * FROM agent_run_events WHERE run_id = ? ORDER BY created_at ASC",
                (run_id,),
            ).fetchall()
        if row is None:
            raise AgentRunNotFoundError(run_id)
        run = self._run_from_row(row)
        return AgentRunWithEvents(**run.model_dump(), events=[self._event_from_row(item) for item in event_rows])

    def update_run_status(self, run_id: str, payload: AgentRunStatusUpdate) -> AgentRunWithEvents:
        run = self.get_run(run_id)
        now = utc_now()
        progress = payload.progress_percent if payload.progress_percent is not None else _progress_for_status(payload.status)
        current_step = payload.current_step or _step_for_status(payload.status)
        metadata = {**run.metadata, **payload.metadata}
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE agent_runs
                SET status = ?, progress_percent = ?, current_step = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload.status.value,
                    progress,
                    current_step,
                    json.dumps(metadata),
                    now.isoformat(),
                    run_id,
                ),
            )
        self.add_event(
            run_id,
            AgentRunEventCreate(
                kind=AgentRunEventKind.STATUS,
                title=f"Status changed to {payload.status.value.replace('_', ' ')}",
                body=current_step or "",
                metadata={"status": payload.status.value, **payload.metadata},
            ),
        )
        return self.get_run(run_id)

    def add_event(self, run_id: str, payload: AgentRunEventCreate) -> AgentRunEventRecord:
        self._ensure_exists(run_id)
        event = AgentRunEventRecord(
            id=f"evt_{uuid4().hex}",
            run_id=run_id,
            kind=payload.kind,
            title=payload.title,
            body=payload.body,
            metadata=payload.metadata,
            created_at=utc_now(),
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_run_events (id, run_id, kind, title, body, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.run_id,
                    event.kind.value,
                    event.title,
                    event.body,
                    json.dumps(event.metadata),
                    event.created_at.isoformat(),
                ),
            )
            connection.execute(
                "UPDATE agent_runs SET updated_at = ? WHERE id = ?",
                (event.created_at.isoformat(), run_id),
            )
        return event

    def _ensure_exists(self, run_id: str) -> None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT id FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise AgentRunNotFoundError(run_id)

    def _run_from_row(self, row) -> AgentRunRecord:
        return AgentRunRecord(
            id=row["id"],
            title=row["title"],
            prompt=row["prompt"],
            mode=row["mode"],
            status=row["status"],
            progress_percent=int(row["progress_percent"]),
            current_step=row["current_step"],
            conversation_id=row["conversation_id"],
            metadata=json.loads(row["metadata_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _event_from_row(self, row) -> AgentRunEventRecord:
        return AgentRunEventRecord(
            id=row["id"],
            run_id=row["run_id"],
            kind=row["kind"],
            title=row["title"],
            body=row["body"],
            metadata=json.loads(row["metadata_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )


def _title_from_prompt(prompt: str) -> str:
    title = " ".join(prompt.split())
    return f"{title[:57]}..." if len(title) > 60 else title or "Agent run"


def _progress_for_status(status: AgentRunStatus) -> int:
    return {
        AgentRunStatus.QUEUED: 0,
        AgentRunStatus.PLANNING: 15,
        AgentRunStatus.RUNNING: 45,
        AgentRunStatus.WAITING_FOR_APPROVAL: 70,
        AgentRunStatus.COMPLETED: 100,
        AgentRunStatus.FAILED: 100,
        AgentRunStatus.CANCELLED: 100,
    }[status]


def _step_for_status(status: AgentRunStatus) -> str:
    return {
        AgentRunStatus.QUEUED: "Queued",
        AgentRunStatus.PLANNING: "Planning the request",
        AgentRunStatus.RUNNING: "Running tools and model steps",
        AgentRunStatus.WAITING_FOR_APPROVAL: "Waiting for approval",
        AgentRunStatus.COMPLETED: "Completed",
        AgentRunStatus.FAILED: "Failed",
        AgentRunStatus.CANCELLED: "Cancelled",
    }[status]

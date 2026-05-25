from __future__ import annotations

import json
from datetime import datetime

from edison_core.database import SQLiteDatabase
from edison_core.schemas import ChatMode, SessionStateRecord, SessionStateUpdate, utc_now


class SessionStateStore:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def initialize(self) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS session_states (
                    session_id TEXT PRIMARY KEY,
                    current_task TEXT,
                    current_project TEXT,
                    active_domain TEXT,
                    last_tool_used TEXT,
                    last_generated_artifact TEXT,
                    task_stage TEXT,
                    last_intent TEXT,
                    current_plan_json TEXT NOT NULL DEFAULT '[]',
                    pending_approval_json TEXT,
                    selected_mode TEXT NOT NULL DEFAULT 'chat',
                    selected_model TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def get_or_create(self, session_id: str) -> SessionStateRecord:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM session_states WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is not None:
            return self._record_from_row(row)
        record = SessionStateRecord(session_id=session_id, updated_at=utc_now())
        self._upsert(record)
        return record

    def update(self, session_id: str, payload: SessionStateUpdate) -> SessionStateRecord:
        current = self.get_or_create(session_id)
        data = current.model_dump()
        for field_name in payload.model_fields_set:
            data[field_name] = getattr(payload, field_name)
        data["updated_at"] = utc_now()
        record = SessionStateRecord(**data)
        self._upsert(record)
        return record

    def _upsert(self, record: SessionStateRecord) -> None:
        pending_approval_json = (
            json.dumps(record.pending_approval) if record.pending_approval is not None else None
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO session_states (
                    session_id,
                    current_task,
                    current_project,
                    active_domain,
                    last_tool_used,
                    last_generated_artifact,
                    task_stage,
                    last_intent,
                    current_plan_json,
                    pending_approval_json,
                    selected_mode,
                    selected_model,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    current_task = excluded.current_task,
                    current_project = excluded.current_project,
                    active_domain = excluded.active_domain,
                    last_tool_used = excluded.last_tool_used,
                    last_generated_artifact = excluded.last_generated_artifact,
                    task_stage = excluded.task_stage,
                    last_intent = excluded.last_intent,
                    current_plan_json = excluded.current_plan_json,
                    pending_approval_json = excluded.pending_approval_json,
                    selected_mode = excluded.selected_mode,
                    selected_model = excluded.selected_model,
                    updated_at = excluded.updated_at
                """,
                (
                    record.session_id,
                    record.current_task,
                    record.current_project,
                    record.active_domain,
                    record.last_tool_used,
                    record.last_generated_artifact,
                    record.task_stage,
                    record.last_intent,
                    json.dumps(record.current_plan),
                    pending_approval_json,
                    _mode_value(record.selected_mode),
                    record.selected_model,
                    record.updated_at.isoformat(),
                ),
            )

    def _record_from_row(self, row) -> SessionStateRecord:
        return SessionStateRecord(
            session_id=row["session_id"],
            current_task=row["current_task"],
            current_project=row["current_project"],
            active_domain=row["active_domain"],
            last_tool_used=row["last_tool_used"],
            last_generated_artifact=row["last_generated_artifact"],
            task_stage=row["task_stage"],
            last_intent=row["last_intent"],
            current_plan=json.loads(row["current_plan_json"]),
            pending_approval=json.loads(row["pending_approval_json"])
            if row["pending_approval_json"]
            else None,
            selected_mode=ChatMode(row["selected_mode"]),
            selected_model=row["selected_model"],
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


def _mode_value(mode: ChatMode | str) -> str:
    return mode.value if isinstance(mode, ChatMode) else mode
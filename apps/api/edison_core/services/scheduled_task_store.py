from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from uuid import uuid4

from edison_core.database import SQLiteDatabase
from edison_core.schemas import (
    ScheduledTaskCreate,
    ScheduledTaskRecord,
    ScheduledTaskUpdate,
    utc_now,
)


class ScheduledTaskNotFoundError(KeyError):
    pass


def compute_next_run(kind: str, time_of_day: str, interval_minutes: int, after: datetime) -> datetime:
    if kind == "interval":
        return after + timedelta(minutes=max(5, int(interval_minutes)))
    try:
        hour_str, minute_str = (time_of_day or "08:00").split(":")
        hour, minute = int(hour_str), int(minute_str)
    except (ValueError, AttributeError):
        hour, minute = 8, 0
    candidate = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= after:
        candidate = candidate + timedelta(days=1)
    return candidate


class ScheduledTaskStore:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def initialize(self) -> None:
        with self.database.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    schedule_kind TEXT NOT NULL DEFAULT 'daily',
                    time_of_day TEXT NOT NULL DEFAULT '08:00',
                    interval_minutes INTEGER NOT NULL DEFAULT 60,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    include_briefing INTEGER NOT NULL DEFAULT 0,
                    last_run_at TEXT,
                    last_status TEXT,
                    last_result TEXT,
                    next_run_at TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    def _row(self, row: sqlite3.Row) -> ScheduledTaskRecord:
        return ScheduledTaskRecord(
            id=row["id"],
            title=row["title"],
            prompt=row["prompt"],
            schedule_kind=row["schedule_kind"],
            time_of_day=row["time_of_day"],
            interval_minutes=row["interval_minutes"],
            enabled=bool(row["enabled"]),
            include_briefing=bool(row["include_briefing"]),
            last_run_at=row["last_run_at"],
            last_status=row["last_status"],
            last_result=row["last_result"],
            next_run_at=row["next_run_at"],
            created_at=row["created_at"],
        )

    def create(self, payload: ScheduledTaskCreate) -> ScheduledTaskRecord:
        task_id = f"sched_{uuid4().hex[:12]}"
        next_run = compute_next_run(
            payload.schedule_kind, payload.time_of_day, payload.interval_minutes, datetime.now()
        ).isoformat()
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO scheduled_tasks (id,title,prompt,schedule_kind,time_of_day,interval_minutes,enabled,include_briefing,next_run_at,created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    task_id,
                    payload.title,
                    payload.prompt,
                    payload.schedule_kind,
                    payload.time_of_day,
                    payload.interval_minutes,
                    int(payload.enabled),
                    int(payload.include_briefing),
                    next_run,
                    utc_now(),
                ),
            )
        return self.get(task_id)

    def list(self) -> list[ScheduledTaskRecord]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM scheduled_tasks ORDER BY created_at DESC").fetchall()
        return [self._row(row) for row in rows]

    def get(self, task_id: str) -> ScheduledTaskRecord:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM scheduled_tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise ScheduledTaskNotFoundError(task_id)
        return self._row(row)

    def update(self, task_id: str, payload: ScheduledTaskUpdate) -> ScheduledTaskRecord:
        current = self.get(task_id)
        merged = current.model_copy(update={k: v for k, v in payload.model_dump(exclude_none=True).items()})
        next_run = compute_next_run(
            merged.schedule_kind, merged.time_of_day, merged.interval_minutes, datetime.now()
        ).isoformat()
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE scheduled_tasks SET title=?,prompt=?,schedule_kind=?,time_of_day=?,interval_minutes=?,enabled=?,include_briefing=?,next_run_at=? WHERE id=?",
                (
                    merged.title,
                    merged.prompt,
                    merged.schedule_kind,
                    merged.time_of_day,
                    merged.interval_minutes,
                    int(merged.enabled),
                    int(merged.include_briefing),
                    next_run,
                    task_id,
                ),
            )
        return self.get(task_id)

    def delete(self, task_id: str) -> None:
        with self.database.connect() as connection:
            connection.execute("DELETE FROM scheduled_tasks WHERE id=?", (task_id,))

    def due(self, now: datetime) -> list[ScheduledTaskRecord]:
        now_iso = now.isoformat()
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM scheduled_tasks WHERE enabled=1 AND next_run_at IS NOT NULL AND next_run_at <= ? ORDER BY next_run_at",
                (now_iso,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def record_run(self, task_id: str, status: str, result: str, ran_at: datetime) -> None:
        task = self.get(task_id)
        next_run = compute_next_run(
            task.schedule_kind, task.time_of_day, task.interval_minutes, ran_at
        ).isoformat()
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE scheduled_tasks SET last_run_at=?,last_status=?,last_result=?,next_run_at=? WHERE id=?",
                (ran_at.isoformat(), status, (result or "")[:4000], next_run, task_id),
            )

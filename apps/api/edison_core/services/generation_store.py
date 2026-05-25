from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from edison_core.database import SQLiteDatabase
from edison_core.schemas import (
    ArtifactCreate,
    ArtifactRecord,
    JobCreate,
    JobEventRecord,
    JobRecord,
    JobStatus,
    JobType,
    utc_now,
)


class JobNotFoundError(ValueError):
    pass


class GenerationStore:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def initialize(self) -> None:
        with self.database.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    path TEXT NOT NULL,
                    mime_type TEXT,
                    source_job_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS generation_jobs (
                    id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    title TEXT NOT NULL,
                    prompt TEXT,
                    backend TEXT NOT NULL,
                    source_artifact_id TEXT,
                    result_artifact_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS job_events (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES generation_jobs(id) ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_generation_jobs_updated
                    ON generation_jobs(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_job_events_job_created
                    ON job_events(job_id, created_at ASC);
                """
            )

    def create_artifact(self, payload: ArtifactCreate) -> ArtifactRecord:
        artifact = ArtifactRecord(id=f"art_{uuid4().hex}", created_at=utc_now(), **payload.model_dump())
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO artifacts (id, kind, title, path, mime_type, source_job_id, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.id,
                    artifact.kind.value,
                    artifact.title,
                    artifact.path,
                    artifact.mime_type,
                    artifact.source_job_id,
                    json.dumps(artifact.metadata),
                    artifact.created_at.isoformat(),
                ),
            )
        return artifact

    def list_artifacts(self, limit: int = 50) -> list[ArtifactRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM artifacts ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._artifact_from_row(row) for row in rows]

    def get_artifact(self, artifact_id: str) -> ArtifactRecord:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
        if row is None:
            raise JobNotFoundError(artifact_id)
        return self._artifact_from_row(row)

    def create_job(self, payload: JobCreate, status: JobStatus = JobStatus.QUEUED) -> JobRecord:
        now = utc_now()
        job = JobRecord(
            id=f"job_{uuid4().hex}",
            status=status,
            created_at=now,
            updated_at=now,
            **payload.model_dump(),
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO generation_jobs (
                    id, job_type, status, title, prompt, backend, source_artifact_id,
                    result_artifact_id, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.job_type.value,
                    job.status.value,
                    job.title,
                    job.prompt,
                    job.backend,
                    job.source_artifact_id,
                    job.result_artifact_id,
                    json.dumps(job.metadata),
                    job.created_at.isoformat(),
                    job.updated_at.isoformat(),
                ),
            )
        self.add_event(job.id, status, f"Job created with status {status.value}")
        return job

    def list_jobs(
        self,
        job_type: JobType | None = None,
        status: JobStatus | None = None,
        limit: int = 50,
    ) -> list[JobRecord]:
        clauses: list[str] = []
        values: list[str | int] = []
        if job_type is not None:
            clauses.append("job_type = ?")
            values.append(job_type.value)
        if status is not None:
            clauses.append("status = ?")
            values.append(status.value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(limit)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM generation_jobs {where} ORDER BY updated_at DESC LIMIT ?",
                values,
            ).fetchall()
        return [self._job_from_row(row) for row in rows]

    def get_job(self, job_id: str) -> JobRecord:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM generation_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise JobNotFoundError(job_id)
        return self._job_from_row(row)

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        message: str,
        metadata: dict | None = None,
    ) -> JobRecord:
        job = self.get_job(job_id)
        now = utc_now()
        merged_metadata = {**job.metadata, **(metadata or {})}
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE generation_jobs SET status = ?, metadata_json = ?, updated_at = ? WHERE id = ?",
                (status.value, json.dumps(merged_metadata), now.isoformat(), job_id),
            )
        self.add_event(job_id, status, message, metadata or {})
        return self.get_job(job_id)

    def finalize_job_result(
        self,
        job_id: str,
        result_artifact_id: str | None,
        status: JobStatus,
        message: str,
        metadata: dict | None = None,
    ) -> JobRecord:
        job = self.get_job(job_id)
        now = utc_now()
        merged_metadata = {**job.metadata, **(metadata or {})}
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE generation_jobs
                SET status = ?, result_artifact_id = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status.value,
                    result_artifact_id,
                    json.dumps(merged_metadata),
                    now.isoformat(),
                    job_id,
                ),
            )
        self.add_event(
            job_id,
            status,
            message,
            {**(metadata or {}), "result_artifact_id": result_artifact_id},
        )
        return self.get_job(job_id)

    def add_event(
        self,
        job_id: str,
        status: JobStatus,
        message: str,
        metadata: dict | None = None,
    ) -> JobEventRecord:
        event = JobEventRecord(
            id=f"evt_{uuid4().hex}",
            job_id=job_id,
            status=status,
            message=message,
            metadata=metadata or {},
            created_at=utc_now(),
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO job_events (id, job_id, status, message, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.job_id,
                    event.status.value,
                    event.message,
                    json.dumps(event.metadata),
                    event.created_at.isoformat(),
                ),
            )
        return event

    def list_events(self, job_id: str) -> list[JobEventRecord]:
        self.get_job(job_id)
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM job_events WHERE job_id = ? ORDER BY created_at ASC",
                (job_id,),
            ).fetchall()
        return [self._event_from_row(row) for row in rows]

    def job_counts(self) -> dict[str, int]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM generation_jobs GROUP BY status"
            ).fetchall()
        return {row["status"]: int(row["count"]) for row in rows}

    def _artifact_from_row(self, row) -> ArtifactRecord:
        return ArtifactRecord(
            id=row["id"],
            kind=row["kind"],
            title=row["title"],
            path=row["path"],
            mime_type=row["mime_type"],
            source_job_id=row["source_job_id"],
            metadata=json.loads(row["metadata_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _job_from_row(self, row) -> JobRecord:
        return JobRecord(
            id=row["id"],
            job_type=row["job_type"],
            status=row["status"],
            title=row["title"],
            prompt=row["prompt"],
            backend=row["backend"],
            source_artifact_id=row["source_artifact_id"],
            result_artifact_id=row["result_artifact_id"],
            metadata=json.loads(row["metadata_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _event_from_row(self, row) -> JobEventRecord:
        return JobEventRecord(
            id=row["id"],
            job_id=row["job_id"],
            status=row["status"],
            message=row["message"],
            metadata=json.loads(row["metadata_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
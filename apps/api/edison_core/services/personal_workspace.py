from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from uuid import uuid4

from edison_core.database import SQLiteDatabase
from edison_core.schemas import (
    DocumentCreate,
    DocumentFormat,
    DocumentRecord,
    DocumentUpdate,
    OrganizerItemCreate,
    OrganizerItemRecord,
    OrganizerItemUpdate,
    OrganizerKind,
    OrganizerStatus,
    SearchCompareResult,
    SearchProvider,
    utc_now,
)


class PersonalWorkspaceNotFoundError(KeyError):
    pass


class PersonalWorkspaceStore:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def initialize(self) -> None:
        with self.database.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS organizer_items (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    due_at TEXT,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_organizer_kind_updated
                    ON organizer_items(kind, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_organizer_status_due
                    ON organizer_items(status, due_at);

                CREATE TABLE IF NOT EXISTS personal_documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    format TEXT NOT NULL DEFAULT 'markdown',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_personal_documents_updated
                    ON personal_documents(updated_at DESC);
                """
            )

    def list_items(
        self,
        kind: OrganizerKind | None = None,
        status: OrganizerStatus | None = None,
        limit: int = 100,
    ) -> list[OrganizerItemRecord]:
        clauses: list[str] = []
        values: list[str | int] = []
        if kind is not None:
            clauses.append("kind = ?")
            values.append(kind.value)
        if status is not None:
            clauses.append("status = ?")
            values.append(status.value)
        values.append(limit)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM organizer_items
                {where}
                ORDER BY
                    CASE WHEN due_at IS NULL THEN 1 ELSE 0 END,
                    due_at ASC,
                    updated_at DESC
                LIMIT ?
                """,
                tuple(values),
            ).fetchall()
        return [self._item_from_row(row) for row in rows]

    def create_item(self, payload: OrganizerItemCreate) -> OrganizerItemRecord:
        now = utc_now()
        item = OrganizerItemRecord(
            id=f"org_{uuid4().hex}",
            created_at=now,
            updated_at=now,
            **payload.model_dump(),
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO organizer_items (
                    id, kind, title, body, status, due_at, tags_json, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.kind.value,
                    item.title,
                    item.body,
                    item.status.value,
                    item.due_at.isoformat() if item.due_at else None,
                    _json_dump(item.tags),
                    _json_dump(item.metadata),
                    item.created_at.isoformat(),
                    item.updated_at.isoformat(),
                ),
            )
        return item

    def update_item(self, item_id: str, payload: OrganizerItemUpdate) -> OrganizerItemRecord:
        current = self.get_item(item_id)
        data = current.model_dump()
        for field_name in payload.model_fields_set:
            data[field_name] = getattr(payload, field_name)
        data["updated_at"] = utc_now()
        item = OrganizerItemRecord(**data)
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE organizer_items
                SET title = ?, body = ?, status = ?, due_at = ?, tags_json = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    item.title,
                    item.body,
                    item.status.value,
                    item.due_at.isoformat() if item.due_at else None,
                    _json_dump(item.tags),
                    _json_dump(item.metadata),
                    item.updated_at.isoformat(),
                    item.id,
                ),
            )
        return item

    def get_item(self, item_id: str) -> OrganizerItemRecord:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM organizer_items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise PersonalWorkspaceNotFoundError(item_id)
        return self._item_from_row(row)

    def delete_item(self, item_id: str) -> None:
        self.get_item(item_id)
        with self.database.connect() as connection:
            connection.execute("DELETE FROM organizer_items WHERE id = ?", (item_id,))

    def list_documents(self, limit: int = 100) -> list[DocumentRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM personal_documents ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._document_from_row(row) for row in rows]

    def create_document(self, payload: DocumentCreate) -> DocumentRecord:
        now = utc_now()
        document = DocumentRecord(
            id=f"doc_{uuid4().hex}",
            created_at=now,
            updated_at=now,
            **payload.model_dump(),
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO personal_documents (
                    id, title, content, format, tags_json, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document.id,
                    document.title,
                    document.content,
                    document.format.value,
                    _json_dump(document.tags),
                    _json_dump(document.metadata),
                    document.created_at.isoformat(),
                    document.updated_at.isoformat(),
                ),
            )
        return document

    def update_document(self, document_id: str, payload: DocumentUpdate) -> DocumentRecord:
        current = self.get_document(document_id)
        data = current.model_dump()
        for field_name in payload.model_fields_set:
            data[field_name] = getattr(payload, field_name)
        data["updated_at"] = utc_now()
        document = DocumentRecord(**data)
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE personal_documents
                SET title = ?, content = ?, format = ?, tags_json = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    document.title,
                    document.content,
                    document.format.value,
                    _json_dump(document.tags),
                    _json_dump(document.metadata),
                    document.updated_at.isoformat(),
                    document.id,
                ),
            )
        return document

    def get_document(self, document_id: str) -> DocumentRecord:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM personal_documents WHERE id = ?", (document_id,)).fetchone()
        if row is None:
            raise PersonalWorkspaceNotFoundError(document_id)
        return self._document_from_row(row)

    def delete_document(self, document_id: str) -> None:
        self.get_document(document_id)
        with self.database.connect() as connection:
            connection.execute("DELETE FROM personal_documents WHERE id = ?", (document_id,))

    def search_documents(self, query: str, max_results: int = 5) -> list[SearchCompareResult]:
        terms = [term for term in re.split(r"\W+", query.lower()) if len(term) > 1]
        if not terms:
            return []
        scored: list[SearchCompareResult] = []
        for document in self.list_documents(limit=200):
            haystack = f"{document.title}\n{document.content}".lower()
            score = sum(haystack.count(term) for term in terms)
            if score <= 0:
                continue
            scored.append(
                SearchCompareResult(
                    provider=SearchProvider.DOCUMENTS,
                    title=document.title,
                    subtitle=document.format.value,
                    snippet=_best_snippet(document.content or document.title, terms),
                    score=float(score),
                    path=document.id,
                    metadata={"document_id": document.id, "tags": document.tags},
                )
            )
        scored.sort(key=lambda item: (-item.score, item.title))
        return scored[:max_results]

    def _item_from_row(self, row: sqlite3.Row) -> OrganizerItemRecord:
        return OrganizerItemRecord(
            id=row["id"],
            kind=OrganizerKind(row["kind"]),
            title=row["title"],
            body=row["body"],
            status=OrganizerStatus(row["status"]),
            due_at=datetime.fromisoformat(row["due_at"]) if row["due_at"] else None,
            tags=_json_load(row["tags_json"], []),
            metadata=_json_load(row["metadata_json"], {}),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _document_from_row(self, row: sqlite3.Row) -> DocumentRecord:
        return DocumentRecord(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            format=DocumentFormat(row["format"]),
            tags=_json_load(row["tags_json"], []),
            metadata=_json_load(row["metadata_json"], {}),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


def _json_dump(value) -> str:
    return json.dumps(value, ensure_ascii=True)


def _json_load(raw: str, fallback):
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def _best_snippet(text: str, terms: list[str], radius: int = 180) -> str:
    clean = " ".join(text.split())
    lower = clean.lower()
    first_index = min((lower.find(term) for term in terms if term in lower), default=0)
    start = max(first_index - radius // 3, 0)
    return clean[start : start + radius]

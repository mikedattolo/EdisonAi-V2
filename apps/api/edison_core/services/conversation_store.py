from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from edison_core.database import SQLiteDatabase
from edison_core.schemas import (
    ConversationCreate,
    ConversationRecord,
    ConversationWithMessages,
    MessageCreate,
    MessageRecord,
    utc_now,
)


class ConversationNotFoundError(ValueError):
    pass


class ConversationStore:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def initialize(self) -> None:
        with self.database.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    memory_enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    model TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
                    ON messages(conversation_id, created_at);
                """
            )

    def create_conversation(self, payload: ConversationCreate) -> ConversationRecord:
        now = utc_now()
        conversation = ConversationRecord(
            id=f"chat_{uuid4().hex}",
            title=(payload.title or "New conversation").strip() or "New conversation",
            mode=payload.mode,
            memory_enabled=payload.memory_enabled,
            created_at=now,
            updated_at=now,
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO conversations (id, title, mode, memory_enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation.id,
                    conversation.title,
                    conversation.mode.value,
                    int(conversation.memory_enabled),
                    conversation.created_at.isoformat(),
                    conversation.updated_at.isoformat(),
                ),
            )
        return conversation

    def list_conversations(self) -> list[ConversationRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM conversations
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [self._conversation_from_row(row) for row in rows]

    def get_conversation(self, conversation_id: str) -> ConversationWithMessages:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if row is None:
                raise ConversationNotFoundError(conversation_id)
            message_rows = connection.execute(
                """
                SELECT * FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
                """,
                (conversation_id,),
            ).fetchall()
        conversation = self._conversation_from_row(row)
        return ConversationWithMessages(
            **conversation.model_dump(),
            messages=[self._message_from_row(message_row) for message_row in message_rows],
        )

    def add_message(self, conversation_id: str, payload: MessageCreate) -> MessageRecord:
        self._ensure_conversation_exists(conversation_id)
        now = utc_now()
        message = MessageRecord(
            id=f"msg_{uuid4().hex}",
            conversation_id=conversation_id,
            role=payload.role,
            content=payload.content,
            model=payload.model,
            metadata=payload.metadata,
            created_at=now,
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO messages (id, conversation_id, role, content, model, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.id,
                    message.conversation_id,
                    message.role.value,
                    message.content,
                    message.model,
                    json.dumps(message.metadata),
                    message.created_at.isoformat(),
                ),
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now.isoformat(), conversation_id),
            )
        return message

    def _ensure_conversation_exists(self, conversation_id: str) -> None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT id FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        if row is None:
            raise ConversationNotFoundError(conversation_id)

    def _conversation_from_row(self, row) -> ConversationRecord:
        return ConversationRecord(
            id=row["id"],
            title=row["title"],
            mode=row["mode"],
            memory_enabled=bool(row["memory_enabled"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _message_from_row(self, row) -> MessageRecord:
        return MessageRecord(
            id=row["id"],
            conversation_id=row["conversation_id"],
            role=row["role"],
            content=row["content"],
            model=row["model"],
            metadata=json.loads(row["metadata_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
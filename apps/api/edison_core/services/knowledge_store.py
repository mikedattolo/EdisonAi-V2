from __future__ import annotations

import io
import json
import os
import re
import sqlite3
import threading
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse
from uuid import uuid4

import httpx

try:
    import numpy as np

    HAVE_NUMPY = True
except ImportError:  # pragma: no cover
    HAVE_NUMPY = False

# Semantic search over the knowledge base uses a local embedding model served by
# Ollama (bge-m3, 1024-dim). Vectors are cached in-process for fast cosine search.
EMBED_MODEL = os.getenv("EDISON_EMBED_MODEL", "bge-m3")
EMBED_OLLAMA_URL = os.getenv("EDISON_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
EMBED_DIM = int(os.getenv("EDISON_EMBED_DIM", "1024"))

from edison_core.database import SQLiteDatabase
from edison_core.schemas import (
    KnowledgeChatImportResult,
    KnowledgeIngestLocalRequest,
    KnowledgeIngestTextRequest,
    KnowledgeSearchMatch,
    KnowledgeStatus,
    KnowledgeSourceRecord,
    utc_now,
)


class KnowledgeIngestError(ValueError):
    pass


# Phrases that mark an assistant brush-off ("I can't access that"). Matches in a
# stored chunk get penalized in search so a prior unhelpful answer doesn't rank
# as the best memory for the same question.
_DISCLAIMER_MARKERS = (
    "i don't have access",
    "i do not have access",
    "i don't have personal information",
    "i don't have any personal information",
    "i don't have access to past conversations",
    "i can't access",
    "i cannot access",
    "i'm not able to access",
    "i am not able to access",
    "i have no memory of",
    "i don't retain",
    "i don't have memory",
    "as an ai language model",
)
_DISCLAIMER_PENALTY = 4.0


class KnowledgeStore:
    def __init__(
        self,
        database: SQLiteDatabase,
        workspace_root: Path,
        http_timeout_seconds: float = 20.0,
    ) -> None:
        self.database = database
        self.workspace_root = workspace_root.resolve()
        self.http_timeout_seconds = http_timeout_seconds
        self._vectors = None  # numpy (N, EMBED_DIM), L2-normalized
        self._vector_ids: list[str] = []
        self._cache_lock = threading.Lock()

    def initialize(self) -> None:
        with self.database.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS knowledge_sources (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    uri TEXT,
                    language TEXT,
                    license TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
                    path TEXT,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    text_lower TEXT NOT NULL,
                    token_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_source
                    ON knowledge_chunks(source_id, chunk_index);
                CREATE INDEX IF NOT EXISTS idx_knowledge_sources_updated
                    ON knowledge_sources(updated_at DESC);

                CREATE TABLE IF NOT EXISTS knowledge_vectors (
                    chunk_id TEXT PRIMARY KEY REFERENCES knowledge_chunks(id) ON DELETE CASCADE,
                    source_id TEXT NOT NULL,
                    vec BLOB NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_vectors_source
                    ON knowledge_vectors(source_id);

                CREATE TABLE IF NOT EXISTS user_profile (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def status(self) -> KnowledgeStatus:
        with self.database.connect() as connection:
            source_count = int(connection.execute("SELECT COUNT(*) FROM knowledge_sources").fetchone()[0])
            chunk_count = int(connection.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0])
            latest = connection.execute("SELECT MAX(updated_at) FROM knowledge_sources").fetchone()[0]
        return KnowledgeStatus(
            source_count=source_count,
            chunk_count=chunk_count,
            latest_ingest_at=datetime.fromisoformat(latest) if latest else None,
        )

    def list_sources(self, limit: int = 100) -> list[KnowledgeSourceRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM knowledge_sources ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._source_from_row(row) for row in rows]

    def ingest_text(self, payload: KnowledgeIngestTextRequest, kind: str = "text") -> KnowledgeSourceRecord:
        chunks = _chunk_text(payload.text)
        if not chunks:
            raise KnowledgeIngestError("No text chunks were produced from this source")

        now = utc_now()
        source = KnowledgeSourceRecord(
            id=f"know_{uuid4().hex}",
            kind=kind,
            title=payload.title,
            uri=payload.uri,
            language=payload.language,
            license=payload.license,
            metadata=payload.metadata,
            chunk_count=len(chunks),
            created_at=now,
            updated_at=now,
        )

        with self.database.connect() as connection:
            self._insert_source(connection, source)
            self._insert_chunks(connection, source.id, chunks, path=_source_path(source))

        return source

    def ingest_url(
        self,
        url: str,
        title: str | None = None,
        language: str | None = None,
        license_name: str | None = None,
    ) -> KnowledgeSourceRecord:
        text = self._download_text(url)
        normalized_title = title or self._title_from_url(url)
        return self.ingest_text(
            KnowledgeIngestTextRequest(
                title=normalized_title,
                text=text,
                uri=url,
                language=language,
                license=license_name,
                metadata={"source": "url"},
            ),
            kind="url",
        )

    def ingest_web_search(self, query: str, max_results: int = 4) -> list[KnowledgeSourceRecord]:
        """Search the web (DuckDuckGo, no API key), fetch the top results, and store them in memory."""
        hits = _duckduckgo_search(query, max_results)
        if not hits:
            raise KnowledgeIngestError(
                "No web results were found (web search may be temporarily unavailable). Try a simpler query."
            )
        records: list[KnowledgeSourceRecord] = []
        errors: list[str] = []
        for title, url in hits:
            try:
                records.append(self.ingest_url(url, title=title or None, license_name="web-search"))
            except Exception as error:  # noqa: BLE001
                errors.append(f"{url}: {error}")
        if not records:
            raise KnowledgeIngestError("Found results but could not fetch any page: " + "; ".join(errors[:3]))
        return records

    def ingest_conversation(self, conversation) -> KnowledgeSourceRecord:
        """Store a chat conversation's transcript in memory so Edison can recall it later."""
        labels = {"user": "User", "assistant": "Assistant", "system": "System", "tool": "Tool"}
        lines: list[str] = []
        for message in (getattr(conversation, "messages", None) or []):
            role = str(getattr(message, "role", "") or "")
            content = (getattr(message, "content", "") or "").strip()
            if not content:
                continue
            lines.append(f"{labels.get(role, role.capitalize() or 'Note')}: {content}")
        transcript = "\n\n".join(lines)
        if not transcript.strip():
            raise KnowledgeIngestError("This conversation has no text to remember yet.")
        convo_id = str(getattr(conversation, "id", "") or "")
        title = (str(getattr(conversation, "title", "") or "").strip()) or "Conversation"
        return self.ingest_text(
            KnowledgeIngestTextRequest(
                title=f"Conversation: {title}"[:240],
                text=transcript,
                uri=f"edison:conversation/{convo_id}" if convo_id else None,
                metadata={"source": "conversation", "conversation_id": convo_id or None},
            ),
            kind="conversation",
        )

    def ingest_wikipedia_page(self, title: str, language: str = "en") -> KnowledgeSourceRecord:
        text = self._download_wikipedia_extract(title, language)
        uri_title = quote(title.replace(" ", "_"))
        wiki_url = f"https://{language}.wikipedia.org/wiki/{uri_title}"
        return self.ingest_text(
            KnowledgeIngestTextRequest(
                title=f"Wikipedia: {title}",
                text=text,
                uri=wiki_url,
                language=language,
                license="CC BY-SA 4.0",
                metadata={"source": "wikipedia", "page_title": title},
            ),
            kind="wikipedia",
        )

    def ingest_local(self, payload: KnowledgeIngestLocalRequest) -> list[KnowledgeSourceRecord]:
        root = (self.workspace_root / payload.path).resolve() if payload.path != "." else self.workspace_root
        if not root.is_relative_to(self.workspace_root):
            raise KnowledgeIngestError("Local ingest path is outside the workspace root")
        if not root.exists():
            raise KnowledgeIngestError(f"Path does not exist: {payload.path}")

        files: list[Path] = []
        for candidate in root.glob(payload.glob):
            if not candidate.is_file():
                continue
            if _looks_binary(candidate):
                continue
            files.append(candidate)
            if len(files) >= payload.max_files:
                break

        records: list[KnowledgeSourceRecord] = []
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            if not text.strip():
                continue
            relative = path.relative_to(self.workspace_root).as_posix()
            records.append(
                self.ingest_text(
                    KnowledgeIngestTextRequest(
                        title=f"Local: {relative}",
                        text=text,
                        uri=relative,
                        metadata={"source": "local", "path": relative},
                    ),
                    kind="local_file",
                )
            )
        return records

    def ingest_chat_export(
        self,
        raw: bytes,
        *,
        filename: str = "",
        source_hint: str = "auto",
        max_conversations: int = 1000,
    ) -> KnowledgeChatImportResult:
        """Import a ChatGPT or Claude data export into the knowledge base.

        ``raw`` is the bytes of an uploaded file. It may be the ``conversations.json``
        from a ChatGPT/Claude export, or the original ``.zip`` archive (the JSON is
        extracted automatically). Each conversation becomes a searchable knowledge source.
        """
        text = _extract_export_json_text(raw, filename)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise KnowledgeIngestError(f"File is not valid JSON: {error}") from error

        conversations = _parse_chat_export(data, source_hint)
        if not conversations:
            raise KnowledgeIngestError(
                "No conversations were found. Upload conversations.json (or the export .zip) "
                "from a ChatGPT or Claude data export."
            )

        detected_values = {conversation.source for conversation in conversations}
        detected = next(iter(detected_values)) if len(detected_values) == 1 else "mixed"

        imported: list[KnowledgeSourceRecord] = []
        skipped = 0
        for conversation in conversations[:max_conversations]:
            if not conversation.transcript.strip():
                skipped += 1
                continue
            try:
                record = self.ingest_text(
                    KnowledgeIngestTextRequest(
                        title=conversation.title[:240],
                        text=conversation.transcript,
                        uri=conversation.uri,
                        metadata={
                            "source": conversation.source,
                            "import_kind": "chat_export",
                            "conversation_id": conversation.conversation_id,
                            "message_count": conversation.message_count,
                            "created_at": conversation.created_at,
                            "origin_filename": filename or None,
                        },
                    ),
                    kind="chat_export",
                )
            except KnowledgeIngestError:
                skipped += 1
                continue
            imported.append(record)

        skipped += max(0, len(conversations) - max_conversations)
        return KnowledgeChatImportResult(
            detected_source=detected,
            conversation_count=len(conversations),
            imported_count=len(imported),
            skipped_count=skipped,
            sources=imported,
        )

    def search(self, query: str, max_results: int = 10) -> list[KnowledgeSearchMatch]:
        terms = [term for term in re.split(r"\W+", query.lower()) if len(term) > 1]
        if not terms:
            return []

        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    chunks.source_id,
                    chunks.path,
                    chunks.text,
                    chunks.text_lower,
                    sources.title,
                    sources.kind,
                    sources.uri
                FROM knowledge_chunks AS chunks
                JOIN knowledge_sources AS sources ON sources.id = chunks.source_id
                ORDER BY sources.updated_at DESC
                """
            ).fetchall()

        scored: list[KnowledgeSearchMatch] = []
        query_lower = " ".join(terms)
        for row in rows:
            text_lower = row["text_lower"]
            title_lower = row["title"].lower()
            term_hits = {term: text_lower.count(term) for term in terms}
            hit_count = sum(term_hits.values())
            if hit_count <= 0:
                continue
            unique_hits = sum(1 for count in term_hits.values() if count > 0)
            title_hits = sum(1 for term in terms if term in title_lower)
            phrase_bonus = 2.5 if query_lower and query_lower in text_lower else 0.0
            score = (
                (unique_hits / max(len(terms), 1)) * 3.0
                + min(hit_count, 12) * 0.18
                + title_hits * 0.35
                + phrase_bonus
            )
            # Down-rank Edison's own "I can't access that" disclaimers so a past
            # unhelpful answer doesn't resurface as the top memory for the same
            # question (a self-reinforcing loop).
            score -= _DISCLAIMER_PENALTY * sum(1 for marker in _DISCLAIMER_MARKERS if marker in text_lower)
            if score <= 0:
                continue
            scored.append(
                KnowledgeSearchMatch(
                    source_id=row["source_id"],
                    source_title=row["title"],
                    source_kind=row["kind"],
                    uri=row["uri"],
                    path=row["path"],
                    score=round(float(score), 4),
                    snippet=_best_snippet(row["text"], terms),
                )
            )

        scored.sort(key=lambda item: (-item.score, item.source_title))
        return scored[:max_results]

    # --- semantic search (bge-m3 embeddings + cosine) ---

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = httpx.post(
            f"{EMBED_OLLAMA_URL}/api/embed",
            json={"model": EMBED_MODEL, "input": texts},
            timeout=180.0,
        )
        response.raise_for_status()
        data = response.json()
        embeddings = data.get("embeddings")
        if not embeddings:
            raise KnowledgeIngestError("Embedding service returned no vectors")
        return embeddings

    def embedding_status(self) -> dict:
        with self.database.connect() as connection:
            total = int(connection.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0])
            embedded = int(connection.execute("SELECT COUNT(*) FROM knowledge_vectors").fetchone()[0])
        return {
            "total_chunks": total,
            "embedded_chunks": embedded,
            "pending": max(total - embedded, 0),
            "model": EMBED_MODEL,
            "ready": HAVE_NUMPY and embedded > 0,
        }

    def embed_pending(self, batch_size: int = 64, max_chunks: int | None = None) -> dict:
        """Embed chunks that don't have a vector yet. Resumable; safe to re-run."""
        if not HAVE_NUMPY:
            return {"embedded": 0, "error": "numpy is not installed on the server"}
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT c.id AS id, c.source_id AS source_id, c.text AS text
                FROM knowledge_chunks AS c
                LEFT JOIN knowledge_vectors AS v ON v.chunk_id = c.id
                WHERE v.chunk_id IS NULL
                LIMIT ?
                """,
                (max_chunks if max_chunks is not None else 10_000_000,),
            ).fetchall()
        total = len(rows)
        done = 0
        for start in range(0, total, batch_size):
            batch = rows[start : start + batch_size]
            texts = [(row["text"] or "")[:2000] for row in batch]
            try:
                vectors = self._embed_batch(texts)
            except (httpx.HTTPError, ValueError, KnowledgeIngestError):
                break
            with self.database.connect() as connection:
                for row, vector in zip(batch, vectors):
                    blob = np.asarray(vector, dtype=np.float32).tobytes()
                    connection.execute(
                        "INSERT OR REPLACE INTO knowledge_vectors (chunk_id, source_id, vec) VALUES (?, ?, ?)",
                        (row["id"], row["source_id"], blob),
                    )
            done += len(batch)
        if done:
            self._invalidate_vector_cache()
        return {"embedded": done, "remaining": max(total - done, 0)}

    def _invalidate_vector_cache(self) -> None:
        with self._cache_lock:
            self._vectors = None
            self._vector_ids = []

    def _ensure_vector_cache(self) -> None:
        if self._vectors is not None:
            return
        with self._cache_lock:
            if self._vectors is not None:
                return
            with self.database.connect() as connection:
                rows = connection.execute("SELECT chunk_id, vec FROM knowledge_vectors").fetchall()
            if not rows:
                self._vector_ids = []
                self._vectors = np.zeros((0, EMBED_DIM), dtype=np.float32)
                return
            matrix = np.empty((len(rows), EMBED_DIM), dtype=np.float32)
            ids: list[str] = []
            valid = 0
            for row in rows:
                vector = np.frombuffer(row["vec"], dtype=np.float32)
                if vector.shape[0] != EMBED_DIM:
                    continue
                matrix[valid] = vector
                ids.append(row["chunk_id"])
                valid += 1
            matrix = matrix[:valid]
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            self._vectors = matrix / norms
            self._vector_ids = ids

    def semantic_search(self, query: str, max_results: int = 10) -> list[KnowledgeSearchMatch]:
        if not HAVE_NUMPY or not query.strip():
            return []
        try:
            self._ensure_vector_cache()
        except sqlite3.Error:
            return []
        if self._vectors is None or len(self._vector_ids) == 0:
            return []
        try:
            query_vector = np.asarray(self._embed_batch([query])[0], dtype=np.float32)
        except (httpx.HTTPError, ValueError, KnowledgeIngestError):
            return []
        norm = float(np.linalg.norm(query_vector)) or 1.0
        query_vector = query_vector / norm
        sims = self._vectors @ query_vector
        k = min(max_results, len(self._vector_ids))
        if k <= 0:
            return []
        top = np.argpartition(-sims, k - 1)[:k]
        top = top[np.argsort(-sims[top])]
        ordered_ids = [self._vector_ids[int(i)] for i in top]
        scores = {self._vector_ids[int(i)]: float(sims[int(i)]) for i in top}

        placeholders = ",".join("?" for _ in ordered_ids)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT chunks.id, chunks.source_id, chunks.path, chunks.text,
                       sources.title, sources.kind, sources.uri
                FROM knowledge_chunks AS chunks
                JOIN knowledge_sources AS sources ON sources.id = chunks.source_id
                WHERE chunks.id IN ({placeholders})
                """,
                ordered_ids,
            ).fetchall()
        by_id = {row["id"]: row for row in rows}
        terms = [term for term in re.split(r"\W+", query.lower()) if len(term) > 1]
        matches: list[KnowledgeSearchMatch] = []
        for chunk_id in ordered_ids:
            row = by_id.get(chunk_id)
            if row is None:
                continue
            similarity = scores.get(chunk_id, 0.0)
            text_lower = (row["text"] or "").lower()
            if any(marker in text_lower for marker in _DISCLAIMER_MARKERS):
                similarity -= 0.25
            matches.append(
                KnowledgeSearchMatch(
                    source_id=row["source_id"],
                    source_title=row["title"],
                    source_kind=row["kind"],
                    uri=row["uri"],
                    path=row["path"],
                    score=round(similarity * 10.0, 4),
                    snippet=_best_snippet(row["text"], terms) if terms else (row["text"] or "")[:280],
                )
            )
        matches.sort(key=lambda item: -item.score)
        return matches[:max_results]

    def hybrid_search(self, query: str, max_results: int = 10) -> list[KnowledgeSearchMatch]:
        """Blend semantic recall (meaning) with keyword hits (exact terms)."""
        semantic = self.semantic_search(query, max_results=max_results)
        keyword = self.search(query, max_results=max_results)
        if not semantic:
            return keyword
        merged: dict[str, KnowledgeSearchMatch] = {}
        for match in semantic:
            merged[match.source_id + "|" + (match.snippet[:40])] = match
        for match in keyword:
            key = match.source_id + "|" + (match.snippet[:40])
            if key not in merged:
                merged[key] = match
        ranked = sorted(merged.values(), key=lambda item: -item.score)
        return ranked[:max_results]

    # --- user profile ("what Edison knows about you", always injected in chat) ---

    def get_user_profile(self) -> dict:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT id, kind, content, updated_at FROM user_profile ORDER BY kind, updated_at"
            ).fetchall()
        summary = ""
        summary_updated = None
        facts: list[dict] = []
        for row in rows:
            if row["kind"] == "summary":
                summary = row["content"]
                summary_updated = row["updated_at"]
            elif row["kind"] == "fact":
                facts.append({"id": row["id"], "content": row["content"], "updated_at": row["updated_at"]})
        return {"summary": summary, "summary_updated_at": summary_updated, "facts": facts}

    def set_user_profile_summary(self, text: str) -> dict:
        now = utc_now().isoformat()
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM user_profile WHERE kind = 'summary' LIMIT 1"
            ).fetchone()
            if existing:
                connection.execute(
                    "UPDATE user_profile SET content = ?, updated_at = ? WHERE id = ?",
                    (text.strip(), now, existing["id"]),
                )
            else:
                connection.execute(
                    "INSERT INTO user_profile (id, kind, content, created_at, updated_at) VALUES (?, 'summary', ?, ?, ?)",
                    (f"prof_{uuid4().hex}", text.strip(), now, now),
                )
        return self.get_user_profile()

    def add_user_fact(self, text: str) -> dict:
        text = text.strip()
        if not text:
            return self.get_user_profile()
        now = utc_now().isoformat()
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO user_profile (id, kind, content, created_at, updated_at) VALUES (?, 'fact', ?, ?, ?)",
                (f"prof_{uuid4().hex}", text, now, now),
            )
        return self.get_user_profile()

    def delete_user_fact(self, fact_id: str) -> dict:
        with self.database.connect() as connection:
            connection.execute("DELETE FROM user_profile WHERE id = ? AND kind = 'fact'", (fact_id,))
        return self.get_user_profile()

    def profile_context_text(self) -> str:
        """Compact profile string injected into every chat turn (empty if unset)."""
        profile = self.get_user_profile()
        parts: list[str] = []
        if profile["summary"]:
            parts.append(profile["summary"].strip())
        if profile["facts"]:
            parts.append("\n".join(f"- {fact['content']}" for fact in profile["facts"][:40]))
        return "\n".join(parts).strip()

    _PROFILE_PROBES = (
        "my name is", "I am a", "I work as a", "my profession is",
        "I am a product designer", "I design products", "my design work",
        "I live in", "where I grew up",
        "my business", "my nonprofit", "my portfolio", "my robotics project", "my fabrication project",
        "my career goal", "what I want to do after school",
        "I studied", "my degree in", "my university", "my major",
        "my work experience", "my internship",
        "my family", "my friends", "my hobbies", "my interests", "sports I play",
        "sustainability and the environment", "about me personally", "who I am as a person",
    )

    # Signals (need 2+) that a chunk is raw code rather than the user's words.
    _CODE_SIGNALS = (
        "edison_core", "apps/api", "apps/web", "routes_", "workspace_agent", "```",
        "def ", "import ", "uvicorn", "systemctl", ".tsx", ".py", "const ", "=>",
    )

    def _looks_like_code(self, text: str) -> bool:
        lowered = (text or "").lower()
        return sum(1 for signal in self._CODE_SIGNALS if signal in lowered) >= 2

    def _retrieve_personal_chunks(self, max_total: int = 22, per_probe: int = 3) -> list[str]:
        """Use semantic search to pull the chunks most likely to describe the user as a person,
        skipping EDISON code/dev chunks that would otherwise dominate the profile."""
        if not HAVE_NUMPY:
            return []
        try:
            self._ensure_vector_cache()
        except sqlite3.Error:
            return []
        if self._vectors is None or len(self._vector_ids) == 0:
            return []
        picked: dict[str, float] = {}
        for probe in self._PROFILE_PROBES:
            try:
                query_vector = np.asarray(self._embed_batch([probe])[0], dtype=np.float32)
            except (httpx.HTTPError, ValueError, KnowledgeIngestError):
                continue
            norm = float(np.linalg.norm(query_vector)) or 1.0
            sims = self._vectors @ (query_vector / norm)
            k = min(per_probe, len(self._vector_ids))
            top = np.argpartition(-sims, k - 1)[:k]
            for index in top:
                chunk_id = self._vector_ids[int(index)]
                score = float(sims[int(index)])
                if chunk_id not in picked or score > picked[chunk_id]:
                    picked[chunk_id] = score
        if not picked:
            return []
        ordered_ids = [cid for cid, _ in sorted(picked.items(), key=lambda kv: -kv[1])]
        placeholders = ",".join("?" for _ in ordered_ids)
        with self.database.connect() as connection:
            # The user's imported ChatGPT/Claude data is kind 'chat_export' (and 'conversation'
            # for remembered chats). Exclude ingested project docs/prompts (local_file/text/url)
            # that frame everything as "EDISON".
            rows = connection.execute(
                f"""
                SELECT chunks.id AS id, chunks.text AS text
                FROM knowledge_chunks AS chunks
                JOIN knowledge_sources AS sources ON sources.id = chunks.source_id
                WHERE chunks.id IN ({placeholders})
                  AND sources.kind IN ('chat_export', 'conversation')
                """,
                ordered_ids,
            ).fetchall()
        by_id = {row["id"]: row["text"] for row in rows}
        texts: list[str] = []
        for cid in ordered_ids:
            text = by_id.get(cid)
            if text and not self._looks_like_code(text):
                texts.append(text)
            if len(texts) >= max_total:
                break
        return texts

    def build_user_profile(self, max_chunks: int = 22, model: str | None = None) -> dict:
        """Extract a durable profile of the user from imported conversations via the local LLM.

        Personal-fact chunks are retrieved semantically first (so the profile captures who the
        user actually is), falling back to a broad random sample only if embeddings aren't ready."""
        model = model or os.getenv("EDISON_PROFILE_MODEL", "local-general-chat")
        texts = self._retrieve_personal_chunks(max_total=max_chunks)
        if not texts:
            with self.database.connect() as connection:
                rows = connection.execute(
                    """
                    SELECT text FROM (
                        SELECT chunks.text AS text, chunks.source_id AS source_id,
                               ROW_NUMBER() OVER (PARTITION BY chunks.source_id ORDER BY chunks.chunk_index) AS rn
                        FROM knowledge_chunks AS chunks
                        JOIN knowledge_sources AS sources ON sources.id = chunks.source_id
                        WHERE sources.kind = 'conversation'
                    )
                    WHERE rn <= 2
                    ORDER BY RANDOM()
                    LIMIT ?
                    """,
                    (max_chunks,),
                ).fetchall()
            texts = [(row["text"] or "") for row in rows]
        if not texts:
            raise KnowledgeIngestError("No conversation memory to build a profile from yet.")
        corpus = "\n\n---\n\n".join((text or "")[:1500] for text in texts)[:110000]
        system = (
            "You are building a rich, durable profile of the USER (the human) from excerpts of their own "
            "past chat conversations. Be comprehensive and specific — capture everything stable and useful "
            "about them. Organize the profile under these markdown headings (omit a heading only if you "
            "truly have nothing for it):\n"
            "**Identity** (full name, location, age/stage),\n"
            "**Work & Education** (profession, role, employer, school, degree, experience),\n"
            "**Projects & Ventures** (businesses, nonprofits, named projects, portfolio pieces),\n"
            "**Skills & Tools** (software, hardware, printers, techniques),\n"
            "**Interests & Values** (hobbies, sports, design philosophy, causes),\n"
            "**Goals** (what they're working toward).\n"
            "Under each heading write concise bullet points with concrete details and names. Aim for 15-30 "
            "bullets total. Use only what the excerpts support; omit anything uncertain. Do NOT mention "
            "'system prompt', 'excerpts', 'conversations', or how you know these things — just state the facts.\n"
            "IMPORTANT: profile the PERSON — their real life, studies, career, and physical/design projects. "
            "Do NOT center the profile on any AI assistant, chatbot, or software platform they are building "
            "together with you; mention such a project at most as a single bullet, not the focus."
        )
        try:
            response = httpx.post(
                f"{EMBED_OLLAMA_URL}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": f"Excerpts from the user's past chats:\n\n{corpus}\n\nComprehensive profile of the user:"},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.2, "num_ctx": 12288},
                },
                timeout=300.0,
            )
            response.raise_for_status()
            content = response.json().get("message", {}).get("content", "").strip()
        except (httpx.HTTPError, ValueError) as error:
            raise KnowledgeIngestError(f"Profile extraction failed: {error.__class__.__name__}") from error
        if not content:
            raise KnowledgeIngestError("The model returned an empty profile.")
        return self.set_user_profile_summary(content)

    def ingest_preset(self, preset: str) -> list[KnowledgeSourceRecord]:
        records: list[KnowledgeSourceRecord] = []
        if preset == "coding-core":
            records.extend(
                [
                    self.ingest_wikipedia_page("Software engineering"),
                    self.ingest_wikipedia_page("Computer programming"),
                    self.ingest_url("https://docs.python.org/3/tutorial/index.html", title="Python Tutorial"),
                    self.ingest_url("https://fastapi.tiangolo.com/", title="FastAPI Documentation"),
                ]
            )
        elif preset == "ai-foundations":
            records.extend(
                [
                    self.ingest_wikipedia_page("Artificial intelligence"),
                    self.ingest_wikipedia_page("Machine learning"),
                    self.ingest_wikipedia_page("Large language model"),
                    self.ingest_url("https://huggingface.co/docs/transformers/index", title="Transformers Documentation"),
                ]
            )
        elif preset == "edison-ops":
            records.append(
                self.ingest_text(
                    KnowledgeIngestTextRequest(
                        title="Edison Operations Playbook",
                        text=EDISON_OPS_KNOWLEDGE,
                        uri="edison:preset/operations",
                        metadata={"source": "preset", "preset": preset},
                    ),
                    kind="preset",
                )
            )
            try:
                records.extend(
                    self.ingest_local(
                        KnowledgeIngestLocalRequest(path="docs", glob="**/*.md", max_files=80)
                    )
                )
            except KnowledgeIngestError:
                pass
        elif preset == "odysseus-features":
            records.append(
                self.ingest_text(
                    KnowledgeIngestTextRequest(
                        title="Odysseus Feature Map for Edison",
                        text=ODYSSEUS_FEATURE_KNOWLEDGE,
                        uri="edison:preset/odysseus-features",
                        license="MIT-derived feature notes",
                        metadata={"source": "preset", "preset": preset},
                    ),
                    kind="preset",
                )
            )
        elif preset == "mcp-agents":
            records.append(
                self.ingest_text(
                    KnowledgeIngestTextRequest(
                        title="MCP and Agent Integration Notes",
                        text=MCP_AGENT_KNOWLEDGE,
                        uri="edison:preset/mcp-agents",
                        metadata={"source": "preset", "preset": preset},
                    ),
                    kind="preset",
                )
            )
        elif preset == "local-ai-hardware":
            records.append(
                self.ingest_text(
                    KnowledgeIngestTextRequest(
                        title="Local AI Hardware Operations",
                        text=LOCAL_AI_HARDWARE_KNOWLEDGE,
                        uri="edison:preset/local-ai-hardware",
                        metadata={"source": "preset", "preset": preset},
                    ),
                    kind="preset",
                )
            )
        elif preset == "business-product-ops":
            records.append(
                self.ingest_text(
                    KnowledgeIngestTextRequest(
                        title="Business and Product Operations for Edison",
                        text=BUSINESS_PRODUCT_OPS_KNOWLEDGE,
                        uri="edison:preset/business-product-ops",
                        metadata={"source": "preset", "preset": preset},
                    ),
                    kind="preset",
                )
            )
        elif preset == "coding-reference":
            records.append(
                self.ingest_text(
                    KnowledgeIngestTextRequest(
                        title="Edison Coding Reference Overview",
                        text=CODING_REFERENCE_OVERVIEW,
                        uri="edison:preset/coding-reference",
                        metadata={"source": "preset", "preset": preset},
                    ),
                    kind="preset",
                )
            )
            try:
                records.extend(
                    self.ingest_local(
                        KnowledgeIngestLocalRequest(path="docs/coding", glob="**/*.md", max_files=50)
                    )
                )
            except KnowledgeIngestError:
                pass
        else:
            raise KnowledgeIngestError(f"Unknown preset: {preset}")
        return records

    def _insert_source(self, connection: sqlite3.Connection, source: KnowledgeSourceRecord) -> None:
        connection.execute(
            """
            INSERT INTO knowledge_sources (
                id, kind, title, uri, language, license, metadata_json, chunk_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source.id,
                source.kind,
                source.title,
                source.uri,
                source.language,
                source.license,
                _json_dump(source.metadata),
                source.chunk_count,
                source.created_at.isoformat(),
                source.updated_at.isoformat(),
            ),
        )

    def _insert_chunks(
        self,
        connection: sqlite3.Connection,
        source_id: str,
        chunks: list[str],
        path: str | None = None,
    ) -> None:
        now = utc_now().isoformat()
        for index, chunk in enumerate(chunks):
            connection.execute(
                """
                INSERT INTO knowledge_chunks (id, source_id, path, chunk_index, text, text_lower, token_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"kchunk_{uuid4().hex}",
                    source_id,
                    path,
                    index,
                    chunk,
                    chunk.lower(),
                    len(chunk.split()),
                    now,
                ),
            )

    def _source_from_row(self, row: sqlite3.Row) -> KnowledgeSourceRecord:
        return KnowledgeSourceRecord(
            id=row["id"],
            kind=row["kind"],
            title=row["title"],
            uri=row["uri"],
            language=row["language"],
            license=row["license"],
            metadata=_json_load(row["metadata_json"]),
            chunk_count=int(row["chunk_count"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _download_text(self, url: str) -> str:
        with httpx.Client(timeout=self.http_timeout_seconds) as client:
            response = client.get(url, follow_redirects=True)
            response.raise_for_status()
        body = response.text
        if "<html" in body.lower():
            return _strip_html(body)
        return body

    def _download_wikipedia_extract(self, title: str, language: str) -> str:
        encoded = quote(title)
        url = (
            f"https://{language}.wikipedia.org/w/api.php"
            f"?action=query&prop=extracts&explaintext=1&format=json&titles={encoded}"
        )
        with httpx.Client(timeout=self.http_timeout_seconds) as client:
            response = client.get(url)
            response.raise_for_status()
        payload = response.json()
        pages = payload.get("query", {}).get("pages", {})
        for page in pages.values():
            extract = page.get("extract")
            if isinstance(extract, str) and extract.strip():
                return extract
        raise KnowledgeIngestError(f"Wikipedia page not found or empty: {title}")

    def _title_from_url(self, url: str) -> str:
        tail = url.rstrip("/").split("/")[-1]
        return tail or url


EDISON_OPS_KNOWLEDGE = """
Edison V2 is a local AI PC control surface. Treat the chat as the primary workflow
and keep advanced controls discoverable without forcing the user to pick technical
modes. Requests should be routed by intent into chat, reasoning, coding, agent, or
media paths. Media results should be delivered inline in chat whenever artifacts
exist, with download links as a backup rather than the main experience.

Core operating priorities:
- Prefer local model and media services when they are healthy.
- Surface setup-required states with direct next actions instead of generic failure text.
- Keep workspace coding projects separate from the Edison application repository.
- Use hardware status, storage status, camera readiness, and knowledge availability
  as context for planning.
- Report fan and accelerator state as operational status, not decorative telemetry.
- Use the knowledge base for Edison docs, hardware setup, MCP capabilities, model
  install notes, and feature implementation details.
""".strip()


ODYSSEUS_FEATURE_KNOWLEDGE = """
Useful Odysseus ideas for Edison, adapted under the MIT license as product and
architecture notes:

- A chat-first home where model choice, memory, tools, and attachments are available
  near the composer rather than scattered across many tabs.
- An agent capability that can use workspace files, web/search tools, shell tools,
  MCP servers, skills, and memory, but is enabled as an explicit toggle for side
  effect-heavy work.
- A memory and skills layer where reusable knowledge can be saved, searched, and
  injected into future prompts.
- Built-in MCP servers for files, browser/web, memory, workspace, and local tools,
  plus integration bundles for clients such as Codex and Claude Code.
- Deep research and document workflows that produce synthesized responses with
  sources rather than raw dumps.
- PWA/mobile-friendly UI patterns, session history, file uploads, theme controls,
  and response streaming.

For Edison, the useful implementation direction is not copying every Odysseus tab.
It is consolidating the best capabilities into Edison chat, knowledge, media,
camera, hardware, and workspace surfaces.
""".strip()


MCP_AGENT_KNOWLEDGE = """
MCP support in Edison should expose capabilities as tools with clear scopes:

- Knowledge MCP: search, ingest text, ingest local files, list sources, and summarize.
- Workspace MCP: search indexed repositories, read approved files, create project
  folders outside the Edison app, preview patches, and run approved commands.
- Media MCP: create and monitor image, video, audio, and 3D jobs; return artifacts.
- Camera MCP: capture a Brio frame, inspect live-feed readiness, and run VLM analysis.
- Hardware MCP: report GPUs, fan policy, storage, Hailo-8 state, camera state, and
  service health.
- Organizer MCP: create and search tasks, notes, calendar items, and documents.

External clients such as Codex and Claude Code should use scoped endpoints and
tokens. Edison should keep the registry visible in settings/system surfaces so the
user can see which servers are ready, staged, or missing.
""".strip()


LOCAL_AI_HARDWARE_KNOWLEDGE = """
Local AI hardware notes for Edison V2:

- NVIDIA GPUs should be detected with driver/runtime checks, memory status, and fan
  control readiness. Fan setting failures should show the underlying service or
  permission issue.
- Hailo-8 PCIe accelerators need the kernel PCIe driver and HailoRT userland
  runtime before `hailortcli` can identify the device. Some Hailo packages are
  distributed through the Hailo Developer Zone and may need to be supplied by the
  owner before installation can complete.
- Logitech Brio camera support should expose a live MJPEG feed, snapshots, and
  VLM/object-recognition analysis. If local accelerator inference is unavailable,
  Edison can still use CPU/GPU VLM analysis with a clear degraded status.
- Storage should favor the largest available data volume for model, dataset, media,
  cache, and workspace directories, while keeping Edison app code and user-created
  code spaces separated.
""".strip()


BUSINESS_PRODUCT_OPS_KNOWLEDGE = """
Business and product operations notes for Edison V2:

- Treat chat as the command center for work, with optional tools for product
  briefs, business planning, design reviews, store operations, print-farm status,
  customer support drafts, and project follow-through.
- Product-design workflows should start from a brief: audience, problem, workflow,
  constraints, assets, success metrics, and the next implementation task.
- Business-management workflows should connect strategy to action: offer, target
  customer, channel, production process, cost/risk notes, metrics, and reminders.
- ToyBox3D should map Shopify products and variants to STL/3MF assets, filament
  colors, printer profiles, queue priority, QA checkpoints, packaging notes, and
  shipping-label status before any automatic print starts.
- Print-farm operations should keep a visible queue, printer health, material
  readiness, camera monitoring, failed-print alerts, order exceptions, and a
  manual approval path for risky or expensive jobs.
- Copilot/Codex-style coding workflows should expose repository search, file
  editing, tests, review, branch context, and clear commit summaries, while keeping
  generated customer projects outside the Edison application repository.
- Claude/ChatGPT-style knowledge workflows should support saved project context,
  artifacts, source-backed research, summaries, response streaming, and simple
  controls near the chat composer.
- Practical dashboards to add next: Shopify orders, production status, printer
  utilization, inventory/materials, revenue/orders, support issues, product design
  backlog, knowledge freshness, and automation health.
""".strip()


def _chunk_text(text: str, chunk_size: int = 1400, overlap: int = 180) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: list[str] = []
    cursor = 0
    total = len(cleaned)
    while cursor < total:
        window = cleaned[cursor: cursor + chunk_size]
        at_end = cursor + chunk_size >= total
        if not at_end:
            split_point = window.rfind(" ")
            if split_point > chunk_size // 2:
                window = window[:split_point]
        chunks.append(window.strip())
        if at_end:
            break
        cursor += max(len(window) - overlap, 1)
    return [chunk for chunk in chunks if chunk]



def _strip_html(raw: str) -> str:
    without_script = re.sub(r"<script.*?>.*?</script>", " ", raw, flags=re.IGNORECASE | re.DOTALL)
    without_style = re.sub(r"<style.*?>.*?</style>", " ", without_script, flags=re.IGNORECASE | re.DOTALL)
    no_tags = re.sub(r"<[^>]+>", " ", without_style)
    return re.sub(r"\s+", " ", no_tags).strip()



def _best_snippet(text: str, terms: list[str], max_chars: int = 280) -> str:
    lower = text.lower()
    best_pos = min((lower.find(term) for term in terms if term in lower), default=0)
    start = max(best_pos - 80, 0)
    snippet = text[start: start + max_chars].strip()
    return snippet if snippet else text[:max_chars].strip()


def _source_path(source: KnowledgeSourceRecord) -> str | None:
    path = source.metadata.get("path")
    if isinstance(path, str) and path.strip():
        return path.strip()
    if source.kind in {"url", "wikipedia"}:
        return source.uri
    return None



def _looks_binary(path: Path) -> bool:
    sample = path.read_bytes()[:1024]
    return b"\x00" in sample



def _json_dump(data: dict) -> str:
    import json

    return json.dumps(data)



def _json_load(value: str) -> dict:
    import json

    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


@dataclass
class _ParsedConversation:
    source: str
    title: str
    transcript: str
    conversation_id: str | None = None
    message_count: int = 0
    created_at: str | None = None
    uri: str | None = None


def _extract_export_json_text(raw: bytes, filename: str) -> str:
    looks_like_zip = raw[:4] == b"PK\x03\x04" or filename.lower().endswith(".zip")
    if looks_like_zip:
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                target = next(
                    (name for name in archive.namelist() if name.lower().endswith("conversations.json")),
                    None,
                )
                if target is None:
                    target = next((name for name in archive.namelist() if name.lower().endswith(".json")), None)
                if target is None:
                    raise KnowledgeIngestError("The zip archive does not contain conversations.json.")
                payload = archive.read(target)
        except zipfile.BadZipFile as error:
            raise KnowledgeIngestError("Uploaded file is not a valid .zip archive.") from error
        return payload.decode("utf-8-sig", errors="replace")
    return raw.decode("utf-8-sig", errors="replace")


def _parse_chat_export(data: object, source_hint: str) -> list[_ParsedConversation]:
    parsed: list[_ParsedConversation] = []
    for convo in _coerce_conversation_list(data):
        if not isinstance(convo, dict):
            continue
        conversation = _render_conversation(convo, source_hint)
        if conversation is not None:
            parsed.append(conversation)
    return parsed


def _coerce_conversation_list(data: object) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("conversations", "data", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        if "mapping" in data or "chat_messages" in data:
            return [data]
    return []


def _render_conversation(convo: dict, source_hint: str) -> _ParsedConversation | None:
    is_chatgpt = isinstance(convo.get("mapping"), dict)
    is_claude = isinstance(convo.get("chat_messages"), list)
    if source_hint == "chatgpt" and is_chatgpt:
        return _render_chatgpt_conversation(convo)
    if source_hint == "claude" and is_claude:
        return _render_claude_conversation(convo)
    if is_chatgpt:
        return _render_chatgpt_conversation(convo)
    if is_claude:
        return _render_claude_conversation(convo)
    return None


def _render_chatgpt_conversation(convo: dict) -> _ParsedConversation | None:
    mapping = convo.get("mapping")
    if not isinstance(mapping, dict):
        return None
    lines: list[str] = []
    count = 0
    for message in _chatgpt_ordered_messages(mapping, convo.get("current_node")):
        if not isinstance(message, dict):
            continue
        metadata = message.get("metadata")
        if isinstance(metadata, dict) and metadata.get("is_visually_hidden_from_conversation"):
            continue
        author = message.get("author")
        role = author.get("role") if isinstance(author, dict) else None
        if role == "system":
            continue
        text = _chatgpt_message_text(message)
        if not text.strip():
            continue
        lines.append(f"{_role_label(role or 'unknown')}: {text.strip()}")
        count += 1
    if count == 0:
        return None
    title = (str(convo.get("title") or "").strip()) or "Untitled ChatGPT conversation"
    conversation_id = (str(convo.get("conversation_id") or convo.get("id") or "")) or None
    return _ParsedConversation(
        source="chatgpt",
        title=f"ChatGPT · {title}",
        transcript="\n\n".join(lines),
        conversation_id=conversation_id,
        message_count=count,
        created_at=_epoch_to_iso(convo.get("create_time")),
        uri=f"chatgpt:conversation/{conversation_id}" if conversation_id else None,
    )


def _chatgpt_ordered_messages(mapping: dict, current_node: object) -> list:
    if isinstance(current_node, str) and current_node in mapping:
        chain: list = []
        cursor: object = current_node
        guard = 0
        while isinstance(cursor, str) and cursor in mapping and guard < 100000:
            node = mapping.get(cursor)
            guard += 1
            if not isinstance(node, dict):
                break
            message = node.get("message")
            if message:
                chain.append(message)
            cursor = node.get("parent")
        if chain:
            chain.reverse()
            return chain
    messages = [
        node["message"]
        for node in mapping.values()
        if isinstance(node, dict) and node.get("message")
    ]
    messages.sort(key=lambda message: (message.get("create_time") or 0) if isinstance(message, dict) else 0)
    return messages


def _chatgpt_message_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts")
    texts: list[str] = []
    if isinstance(parts, list):
        for part in parts:
            if isinstance(part, str):
                texts.append(part)
            elif isinstance(part, dict):
                if isinstance(part.get("text"), str):
                    texts.append(part["text"])
                elif part.get("content_type") == "image_asset_pointer":
                    texts.append("[image]")
    if texts:
        return "\n".join(text for text in texts if text)
    if isinstance(content.get("text"), str):
        return content["text"]
    return ""


def _render_claude_conversation(convo: dict) -> _ParsedConversation | None:
    messages = convo.get("chat_messages")
    if not isinstance(messages, list):
        return None
    lines: list[str] = []
    count = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        sender = message.get("sender") or message.get("role") or "unknown"
        text = _claude_message_text(message)
        if not text.strip():
            continue
        lines.append(f"{_role_label(str(sender))}: {text.strip()}")
        count += 1
    if count == 0:
        return None
    title = (str(convo.get("name") or convo.get("title") or "").strip()) or "Untitled Claude conversation"
    conversation_id = (str(convo.get("uuid") or convo.get("id") or "")) or None
    return _ParsedConversation(
        source="claude",
        title=f"Claude · {title}",
        transcript="\n\n".join(lines),
        conversation_id=conversation_id,
        message_count=count,
        created_at=_iso_or_none(convo.get("created_at")),
        uri=f"claude:conversation/{conversation_id}" if conversation_id else None,
    )


def _claude_message_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, list):
        texts: list[str] = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                texts.append(block["text"])
        if texts:
            return "\n".join(texts)
    text = message.get("text")
    return text if isinstance(text, str) else ""


def _role_label(role: str) -> str:
    normalized = (role or "").lower()
    if normalized in {"user", "human"}:
        return "User"
    if normalized == "assistant":
        return "Assistant"
    if normalized == "tool":
        return "Tool"
    if normalized == "system":
        return "System"
    return (role or "Unknown").capitalize()


def _epoch_to_iso(value: object) -> str | None:
    if isinstance(value, (int, float)) and value > 0:
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _iso_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _duckduckgo_search(query: str, max_results: int = 4) -> list[tuple[str, str]]:
    """Return up to max_results (title, url) pairs from DuckDuckGo's HTML endpoint (no API key)."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0 Safari/537.36"
        )
    }
    try:
        with httpx.Client(timeout=15.0, headers=headers, follow_redirects=True) as client:
            response = client.get("https://html.duckduckgo.com/html/", params={"q": query})
            response.raise_for_status()
        html = response.text
    except httpx.HTTPError:
        return []
    results: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in re.finditer(
        r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    ):
        url = _ddg_resolve_url(match.group(1))
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        if url and url.startswith("http") and url not in seen:
            seen.add(url)
            results.append((title, url))
        if len(results) >= max_results:
            break
    return results


def _ddg_resolve_url(href: str) -> str:
    href = href.strip()
    if href.startswith("//"):
        href = "https:" + href
    try:
        parsed = urlparse(href)
    except ValueError:
        return ""
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [None])[0]
        if target:
            return unquote(target)
    return href


CODING_REFERENCE_OVERVIEW = """
Edison Coding Reference: a built-in knowledge base for writing and editing code on this machine.
Detailed guides live in docs/coding/ and cover:
- edison-environment: the Ubuntu box, repo layout, services, how to edit/build/run/restart, and how to get dependencies here.
- dependency-management: how to add/install/pin dependencies in Python (pip+venv), Node (npm/pnpm/yarn), Java (Maven/Gradle), and system packages (apt).
- python, javascript-typescript, java: language syntax, tooling, idioms, and common gotchas.
- html, css, react-vite: web frontend - page structure, styling, and Edison's own React + Vite + TypeScript stack.
- bash-linux: shell and Linux commands for operating the box.
- git: version-control workflow (the code agent uses read-only git only).
- debugging-and-testing: a reliable debugging loop and how to verify changes per stack.
When coding, prefer the project's existing tools and patterns. On Edison that means pip + the .venv for the API and npm for the web app, surgical edits over full-file rewrites, and an import-check/build plus a service restart to apply changes.
""".strip()


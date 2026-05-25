from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import httpx

from edison_core.database import SQLiteDatabase
from edison_core.schemas import (
    KnowledgeIngestLocalRequest,
    KnowledgeIngestTextRequest,
    KnowledgeSearchMatch,
    KnowledgeStatus,
    KnowledgeSourceRecord,
    utc_now,
)


class KnowledgeIngestError(ValueError):
    pass


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
            self._insert_chunks(connection, source.id, chunks)

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
                    sources.kind
                FROM knowledge_chunks AS chunks
                JOIN knowledge_sources AS sources ON sources.id = chunks.source_id
                ORDER BY sources.updated_at DESC
                """
            ).fetchall()

        scored: list[KnowledgeSearchMatch] = []
        for row in rows:
            text_lower = row["text_lower"]
            hit_count = sum(text_lower.count(term) for term in terms)
            if hit_count <= 0:
                continue
            score = hit_count / max(len(terms), 1)
            scored.append(
                KnowledgeSearchMatch(
                    source_id=row["source_id"],
                    source_title=row["title"],
                    source_kind=row["kind"],
                    path=row["path"],
                    score=round(float(score), 4),
                    snippet=_best_snippet(row["text"], terms),
                )
            )

        scored.sort(key=lambda item: (-item.score, item.source_title))
        return scored[:max_results]

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

    def _insert_chunks(self, connection: sqlite3.Connection, source_id: str, chunks: list[str]) -> None:
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
                    None,
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



def _chunk_text(text: str, chunk_size: int = 1400, overlap: int = 180) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: list[str] = []
    cursor = 0
    while cursor < len(cleaned):
        window = cleaned[cursor: cursor + chunk_size]
        if cursor + chunk_size < len(cleaned):
            split_point = window.rfind(" ")
            if split_point > chunk_size // 2:
                window = window[:split_point]
        chunks.append(window.strip())
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

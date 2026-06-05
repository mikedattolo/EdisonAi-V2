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
